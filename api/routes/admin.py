"""
Admin API — единое место для всех токенов и конфигов.
POST /api/v1/admin/config — записать значение
GET  /api/v1/admin/config — получить все настройки (секреты замаскированы)
POST /api/v1/admin/notify/reply — ответ Архитектора на уведомление
"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
from core.config_manager import get, set as cfg_set, get_all, CONFIG_SCHEMA

router = APIRouter()

def _check_admin(token: str = Header(None, alias="X-Admin-Token")):
    secret = os.getenv("EVO_API_SECRET", "")
    if not secret:
        if os.getenv("EVO_ENV", "production") == "production":
            raise HTTPException(500, "EVO_API_SECRET не задан")
        secret = "dev_admin_secret"  # только development
    if not token or token != secret:
        raise HTTPException(403, "Invalid admin token")

class ConfigItem(BaseModel):
    key: str
    value: str

class NotifyReply(BaseModel):
    notification_id: int
    choice: int

@router.post("/admin/config")
async def set_config(item: ConfigItem,
                     token: str = Header(None, alias="X-Admin-Token")):
    _check_admin(token)
    schema = CONFIG_SCHEMA.get(item.key, ("general", ""))
    await cfg_set(item.key, item.value,
                  description=schema[1], category=schema[0])
    return {"status": "ok", "key": item.key}

@router.get("/admin/config")
async def get_config(category: Optional[str] = None,
                     token: str = Header(None, alias="X-Admin-Token")):
    _check_admin(token)
    items = await get_all(category)
    schema_keys = list(CONFIG_SCHEMA.keys())
    return {"config": items, "available_keys": schema_keys}

@router.post("/admin/notify/reply")
async def notify_reply(req: NotifyReply,
                        token: str = Header(None, alias="X-Admin-Token")):
    _check_admin(token)
    from core.sleep_mode import apply_architect_choice
    result = await apply_architect_choice(req.notification_id, req.choice)
    return result

@router.get("/admin/shards/test")
async def test_shards(token: str = Header(None, alias="X-Admin-Token")):
    """Тест подключения к шарду — проверить что провайдер работает."""
    _check_admin(token)
    from shards.shard_client import write_cell, read_cell
    test_path = "/evo/TEST/connection_test.zst"
    try:
        final = await write_cell("", test_path, "EVO-core shard test OK")
        content, _ = await read_cell("", test_path)
        ok = "EVO-core shard test OK" in content
        return {"status": "ok" if ok else "fail", "path": final, "content": content}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Управление пользователями и API ключами ───────────────────────────────────

class CreateUserReq(BaseModel):
    email: str
    plan: str = "free"

@router.post("/admin/users")
async def create_user(req: CreateUserReq,
                      token: str = Header(None, alias="X-Admin-Token")):
    """Создать пользователя и получить API ключ."""
    _check_admin(token)
    from db.users import create_user as _create
    user = await _create(req.email, req.plan)
    # Не возвращаем полный API ключ — только маскированный
    key = user['api_key']
    user['api_key_masked'] = key[:8] + "****" + key[-4:]
    user['api_key_full'] = key  # только в ответе на создание
    return user

@router.post("/admin/users/{user_id}/rotate-key")
async def rotate_user_key(user_id: str,
                           token: str = Header(None, alias="X-Admin-Token")):
    """Ротация API ключа пользователя."""
    _check_admin(token)
    from db.users import rotate_api_key
    new_key = await rotate_api_key(user_id)
    return {"status": "ok", "new_key": new_key[:8] + "****" + new_key[-4:],
            "new_key_full": new_key}

@router.delete("/admin/users/{user_id}")
async def deactivate_user(user_id: str,
                           token: str = Header(None, alias="X-Admin-Token")):
    """Деактивировать пользователя."""
    _check_admin(token)
    from db.users import deactivate_user as _deactivate
    await _deactivate(user_id)
    return {"status": "deactivated", "user_id": user_id}

@router.get("/admin/audit-log")
async def get_audit_log(limit: int = 50,
                         token: str = Header(None, alias="X-Admin-Token")):
    """Audit log всех изменений конфигов."""
    _check_admin(token)
    from db.pg_client import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ts, action, actor, target, value_hash, ip
            FROM evo_audit_log ORDER BY ts DESC LIMIT $1
        """, limit)
    return {"audit_log": [dict(r) for r in rows]}


# ── Живые прогоны — реальные проверки, не заглушки ─────────────────────────

@router.post("/admin/live-test")
async def run_live_test(token: str = Header(None, alias="X-Admin-Token")):
    """
    Прогоняет реальные проверки основных узлов ядра прямо на этом
    инстансе (не мок): БД, Redis, эмбеддинг-провайдер, шард-хранилище,
    поиск в библиотеке, HMAC-подпись. Возвращает pass/fail + латентность +
    текст ошибки по каждой — для "что и где упало" на живом деплое.
    """
    _check_admin(token)
    import time
    checks = []

    async def _run(name: str, fn):
        t0 = time.monotonic()
        try:
            detail = await fn()
            checks.append({
                "check": name, "status": "ok",
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "detail": detail or "OK",
            })
        except Exception as e:
            checks.append({
                "check": name, "status": "fail",
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "detail": str(e)[:300],
            })

    async def check_postgres():
        from db.pg_client import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return "Соединение и запрос выполнены"

    async def check_redis():
        from db.redis_client import get_redis
        r = await get_redis()
        await r.ping()
        return "PONG получен"

    async def check_embedding():
        from core.ai_router import ai_router
        vec = await ai_router.embed("live test проверка эмбеддинга")
        if not vec or len(vec) != 768:
            raise RuntimeError(f"Неожиданная размерность вектора: {len(vec) if vec else 0}")
        return f"Вектор размерности {len(vec)} получен"

    async def check_shard_storage():
        from shards.shard_client import write_cell, read_cell
        test_path = "/evo/TEST/live_test_check.zst"
        marker = f"live-test-{int(time.time())}"
        await write_cell("", test_path, marker)
        content, _ = await read_cell("", test_path)
        if marker not in content:
            raise RuntimeError("Записанное содержимое не совпало при чтении")
        return "Запись/чтение ячейки шарда пройдены"

    async def check_library_search():
        from core.librarian import search
        result = await search(
            query_text="live test проверка поиска библиотеки",
            plan_steps=[], stack=[], session_id="live_test_internal"
        )
        return f"scenario={result.get('scenario')}, символов={len(result.get('symbols', []))}"

    async def check_signature():
        from core.signature import _compute
        sig1 = _compute({"a": 1}, "test_key")
        sig2 = _compute({"a": 1}, "test_key")
        if sig1 != sig2:
            raise RuntimeError("Подпись не детерминирована")
        return "HMAC детерминирован"

    await _run("PostgreSQL", check_postgres)
    await _run("Redis", check_redis)
    await _run("Gemini Embedding", check_embedding)
    await _run("Shard Storage (write/read)", check_shard_storage)
    await _run("Library Search (librarian.search)", check_library_search)
    await _run("HMAC Signature", check_signature)

    passed = sum(1 for c in checks if c["status"] == "ok")
    return {
        "summary": f"{passed}/{len(checks)} passed",
        "all_passed": passed == len(checks),
        "checks": checks,
    }


@router.get("/admin/errors")
async def get_recent_errors(limit: int = 50,
                             token: str = Header(None, alias="X-Admin-Token")):
    """Последние упавшие запросы — что и где упало, по каждому пользователю."""
    _check_admin(token)
    from db.pg_client import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT l.ts, l.endpoint, l.error_type, l.latency_ms,
                   l.session_id, u.email
            FROM evo_request_log l
            LEFT JOIN evo_users u ON u.id = l.user_id
            WHERE l.status = 'error'
            ORDER BY l.ts DESC LIMIT $1
        """, limit)
    return {"errors": [
        {
            "ts": r["ts"].isoformat() if r["ts"] else None,
            "endpoint": r["endpoint"],
            "error_type": r["error_type"],
            "latency_ms": r["latency_ms"],
            "session_id": r["session_id"],
            "user_email": r["email"] or "неизвестен",
        } for r in rows
    ]}


@router.get("/admin/users-metrics")
async def get_users_metrics(limit: int = 100,
                             token: str = Header(None, alias="X-Admin-Token")):
    """
    Таблица по каждому пользователю: запросы/латентность/токены за 30 дней
    — для сводной админки владельца. Источник: evo_request_log (миграция 009).
    """
    _check_admin(token)
    from db.pg_client import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT u.id, u.email, u.plan, u.is_active, u.last_seen,
                   COUNT(l.id) as requests_30d,
                   AVG(l.latency_ms)::float as avg_latency_ms,
                   COALESCE(SUM(l.tokens_actual), 0) as tokens_actual,
                   COALESCE(SUM(l.tokens_baseline_est), 0) as tokens_baseline_est,
                   COUNT(l.id) FILTER (WHERE l.status = 'error') as errors_30d
            FROM evo_users u
            LEFT JOIN evo_request_log l
                ON l.user_id = u.id AND l.ts > NOW() - INTERVAL '30 days'
            GROUP BY u.id, u.email, u.plan, u.is_active, u.last_seen
            ORDER BY requests_30d DESC NULLS LAST
            LIMIT $1
        """, limit)
    result = []
    for r in rows:
        tokens_actual = int(r["tokens_actual"] or 0)
        tokens_baseline = int(r["tokens_baseline_est"] or 0)
        result.append({
            "user_id": str(r["id"]),
            "email": r["email"],
            "plan": r["plan"],
            "is_active": r["is_active"],
            "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            "requests_30d": int(r["requests_30d"] or 0),
            "avg_latency_ms": round(r["avg_latency_ms"] or 0, 1),
            "errors_30d": int(r["errors_30d"] or 0),
            "tokens_actual": tokens_actual,
            "tokens_baseline_est": tokens_baseline,
            "tokens_saved": max(0, tokens_baseline - tokens_actual),
        })
    return {"users": result}


# ── Сводная статистика ядра — для админ-панели ────────────────────────────────

@router.get("/admin/background-stats")
async def get_background_stats(token: str = Header(None, alias="X-Admin-Token")):
    """Фоновая работа Sleep Mode за 30 дней — дубль того, что видит юзер в ЛК."""
    _check_admin(token)
    from db.pg_client import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COALESCE(SUM(symbols_actualized),0) as symbols_actualized,
                   COALESCE(SUM(ligatures_formed),0) as ligatures_formed,
                   COALESCE(SUM(integrity_fixes),0) as integrity_fixes,
                   COALESCE(SUM(tokens_saved_theoretical),0) as tokens_saved_theoretical
            FROM evo_background_stats WHERE day > NOW() - INTERVAL '30 days'
        """)
        daily = await conn.fetch("""
            SELECT day, symbols_actualized, ligatures_formed, integrity_fixes,
                   tokens_saved_theoretical
            FROM evo_background_stats WHERE day > NOW() - INTERVAL '30 days'
            ORDER BY day ASC
        """)
    return {
        "totals": dict(row),
        "daily": [dict(r) | {"day": r["day"].isoformat()} for r in daily],
    }


@router.get("/admin/stats")
async def get_core_stats(token: str = Header(None, alias="X-Admin-Token")):
    """
    Сводная статистика Языка-Библиотеки и пользователей.
    Источники: scl_symbols, evo_users, evo_sessions, evo_notifications.
    """
    _check_admin(token)
    from db.pg_client import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_symbols = await conn.fetchval(
            "SELECT COUNT(*) FROM scl_symbols WHERE is_legacy=FALSE"
        )
        legacy_symbols = await conn.fetchval(
            "SELECT COUNT(*) FROM scl_symbols WHERE is_legacy=TRUE"
        )
        auto_collected = await conn.fetchval(
            "SELECT COUNT(*) FROM scl_symbols WHERE auto_collected=TRUE AND is_legacy=FALSE"
        )
        ligature_candidates = await conn.fetchval(
            "SELECT COUNT(*) FROM scl_symbols WHERE confirmed_by >= 3 AND is_legacy=FALSE"
        )
        by_root = await conn.fetch(
            "SELECT science, COUNT(*) as cnt, AVG(rating_frequency)::float as avg_rf "
            "FROM scl_symbols WHERE is_legacy=FALSE "
            "GROUP BY science ORDER BY cnt DESC LIMIT 12"
        )
        top_symbols = await conn.fetch(
            "SELECT id, label, rating_frequency, confirmed_by FROM scl_symbols "
            "WHERE is_legacy=FALSE ORDER BY rating_frequency DESC LIMIT 8"
        )
        pending_notifications = await conn.fetchval(
            "SELECT COUNT(*) FROM evo_notifications WHERE status='pending'"
        )
        users_by_plan = await conn.fetch(
            "SELECT plan, COUNT(*) as cnt FROM evo_users WHERE is_active=TRUE GROUP BY plan"
        )
        total_users = await conn.fetchval("SELECT COUNT(*) FROM evo_users WHERE is_active=TRUE")
        active_sessions = await conn.fetchval(
            "SELECT COUNT(*) FROM evo_sessions WHERE is_active=TRUE AND expires_at > NOW()"
        )

    return {
        "library": {
            "total_symbols": total_symbols,
            "legacy_symbols": legacy_symbols,
            "auto_collected_channel1": auto_collected,
            "ligature_candidates": ligature_candidates,
            "by_macro_root": [dict(r) for r in by_root],
            "top_by_rating": [dict(r) for r in top_symbols],
        },
        "operations": {
            "pending_architect_notifications": pending_notifications,
            "active_flagship_sessions": active_sessions,
        },
        "users": {
            "total_active": total_users,
            "by_plan": {r["plan"]: r["cnt"] for r in users_by_plan},
        },
    }
