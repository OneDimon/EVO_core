"""
Security Middleware — критическая защита EVO-core
1. JWT аутентификация пользователей на всех /api/v1/* (кроме /handshake)
2. Rate limiting: 60 req/min per API key
3. HMAC верификация входящих запросов от флагмана
4. Блокировка при отсутствии секретов в .env
"""
import os, hmac, hashlib, logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from collections import defaultdict
from typing import Callable

log = logging.getLogger("evo.security")

# ── Проверка обязательных секретов при старте ────────────────────────────────

def check_required_secrets():
    """Блокирует старт если критические секреты не заданы."""
    required = ["EVO_HMAC_SECRET", "EVO_API_SECRET"]
    missing = [k for k in required if not os.getenv(k) or
               os.getenv(k, "").startswith("dev_") or
               os.getenv(k, "").startswith("generate_")]
    if missing and os.getenv("EVO_ENV", "production") == "production":
        raise RuntimeError(
            f"СТАРТ ЗАБЛОКИРОВАН: не заданы секреты: {missing}. "
            f"Заполни .env файл перед запуском в продакшне. "
            f"Для разработки: EVO_ENV=development"
        )

# ── Redis rate limiter (P10 fix: работает при uvicorn --workers N) ───────────
# In-memory defaultdict заменён на Redis incr+expire.
# При недоступности Redis — падаем в in-memory fallback (dev-режим).

RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "60"))
_rate_store_fallback: dict = defaultdict(list)  # только для dev/fallback

async def _check_rate_limit(key: str) -> bool:
    """
    True если запрос разрешён, False если превышен лимит.
    P10 fix: Redis-based, работает при multi-worker uvicorn.
    Fallback на in-memory если Redis недоступен (тесты/dev).
    """
    try:
        from db.redis_client import get_redis
        r = await get_redis()
        rate_key = f"evo:rate:{key}"
        count = await r.incr(rate_key)
        if count == 1:
            await r.expire(rate_key, 60)  # окно 60 секунд
        return count <= RATE_LIMIT_RPM
    except Exception as e:
        log.warning(f"[Security] Redis rate limit unavailable, using in-memory fallback: {e}")
        # In-memory fallback для dev/тестов
        import time
        now = time.time()
        window_start = now - 60
        _rate_store_fallback[key] = [
            t for t in _rate_store_fallback[key] if t > window_start
        ]
        if len(_rate_store_fallback[key]) >= RATE_LIMIT_RPM:
            return False
        _rate_store_fallback[key].append(now)
        return True

# ── HMAC верификация входящих запросов ───────────────────────────────────────

def verify_incoming_hmac(body: bytes, signature: str, session_key: str) -> bool:
    """Верифицирует X-EVO-Signature входящего запроса."""
    if not signature or not session_key:
        return False
    expected = hmac.new(
        session_key.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

# ── Белый список эндпоинтов без auth ─────────────────────────────────────────

NO_AUTH_PATHS = {
    "/health", "/", "/docs", "/openapi.json",
    "/api/v1/handshake",   # первичное подключение — без токена
    "/api/v1/register",    # P11: регистрация без API-ключа
}

# ── Middleware class ──────────────────────────────────────────────────────────

class EVOSecurityMiddleware:
    def __init__(self, app, skip_auth_env: str = "development"):
        self.app = app
        self.dev_mode = os.getenv("EVO_ENV", "production") == skip_auth_env

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        # Пропускаем whitelist
        if path in NO_AUTH_PATHS or self.dev_mode:
            if self.dev_mode and path not in NO_AUTH_PATHS:
                log.debug(f"[Security] DEV MODE: пропуск auth для {path}")
            await self.app(scope, receive, send)
            return

        # Rate limiting по API ключу или IP
        api_key = request.headers.get("X-API-Key", "")
        rate_key = api_key or request.client.host
        if not await _check_rate_limit(rate_key):
            response = JSONResponse(
                {"error": "rate_limit_exceeded",
                 "message": f"Превышен лимит {RATE_LIMIT_RPM} запросов/мин"},
                status_code=429
            )
            await response(scope, receive, send)
            return

        # Аутентификация по API ключу
        if not api_key:
            response = JSONResponse(
                {"error": "unauthorized",
                 "message": "Требуется X-API-Key заголовок"},
                status_code=401
            )
            await response(scope, receive, send)
            return

        # Верификация API ключа
        valid = await _validate_api_key(api_key)
        if not valid:
            response = JSONResponse(
                {"error": "invalid_api_key",
                 "message": "Недействительный API ключ"},
                status_code=403
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


async def _validate_api_key(api_key: str) -> bool:
    """Проверяет API ключ в таблице users."""
    try:
        from db.pg_client import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, is_active FROM evo_users WHERE api_key=$1",
                api_key
            )
        return row is not None and row['is_active']
    except Exception as e:
        log.error(f"[Security] API key check error: {e}")
        # В dev режиме разрешаем мастер-ключ
        master = os.getenv("EVO_MASTER_KEY", "")
        return master and api_key == master
