"""
GET /api/v1/me — личный кабинет пользователя.
Возвращает данные аккаунта и статистику использования по собственному API-ключу.
Связан с: db/users.py (evo_users, evo_api_keys), db/migrations/
003_users_security.sql, 009_metrics_and_api_keys.sql.
"""
import logging
import secrets
import hashlib
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from db.pg_client import get_pool
from db.users import get_user_by_any_key

log = logging.getLogger("evo.me")
router = APIRouter()

PLAN_LIMITS = {
    "free": {"requests_per_month": 5000, "shards_visible": 1},
    "pro": {"requests_per_month": 50000, "shards_visible": 3},
    "enterprise": {"requests_per_month": None, "shards_visible": None},
}


async def _current_user(x_api_key: str) -> dict:
    if not x_api_key:
        raise HTTPException(401, "Требуется X-API-Key")
    user = await get_user_by_any_key(x_api_key)
    if not user:
        raise HTTPException(403, "Недействительный или отключённый ключ")
    return user


@router.get("/me")
async def get_me(x_api_key: str = Header(None, alias="X-API-Key")):
    """Личный кабинет: профиль + использование за текущий месяц."""
    user = await _current_user(x_api_key)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Статистика запросов за последние 30 дней из evo_rate_stats
        usage = await conn.fetchval(
            "SELECT COALESCE(SUM(req_count), 0) FROM evo_rate_stats "
            "WHERE ip_or_key=$1 AND window_ts > NOW() - INTERVAL '30 days'",
            x_api_key
        )
        # Сессии флагмана за тот же период
        sessions = await conn.fetchval(
            "SELECT COUNT(*) FROM evo_sessions WHERE user_id=$1 "
            "AND created_at > NOW() - INTERVAL '30 days'",
            user["id"]
        )

    plan = user["plan"] or "free"
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

    return {
        "email": user["email"],
        "plan": plan,
        "member_since": user["created_at"].isoformat() if user["created_at"] else None,
        "last_seen": user["last_seen"].isoformat() if user["last_seen"] else None,
        "usage": {
            "requests_30d": int(usage or 0),
            "flagship_sessions_30d": int(sessions or 0),
            "limit_per_month": limits["requests_per_month"],
        },
        "settings": {
            "default_execution_mode": user.get("default_execution_mode") or "stepwise",
        },
        "api_key_masked": x_api_key[:8] + "****" + x_api_key[-4:],
    }


class UpdateSettingsReq(BaseModel):
    default_execution_mode: str


@router.put("/me/settings")
async def update_settings(req: UpdateSettingsReq,
                           x_api_key: str = Header(None, alias="X-API-Key")):
    """
    Предпочтение по умолчанию: 'stepwise' — видно прогресс по шагам через
    /step_done; 'auto' — ядро сразу отдаёт весь план целиком. Применяется,
    только когда флагман сам не указал execution_mode явно в /query —
    сессия важнее умолчания (см. api/routes/query.py).
    """
    if req.default_execution_mode not in ("stepwise", "auto"):
        raise HTTPException(400, "default_execution_mode: 'stepwise' или 'auto'")
    user = await _current_user(x_api_key)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE evo_users SET default_execution_mode=$2 WHERE id=$1",
            user["id"], req.default_execution_mode
        )
    return {"status": "ok", "default_execution_mode": req.default_execution_mode}


# ── API-ключи — создание/список/отзыв самим пользователем ──────────────────

class CreateApiKeyReq(BaseModel):
    label: str = "API ключ"


@router.get("/me/api-keys")
async def list_api_keys(x_api_key: str = Header(None, alias="X-API-Key")):
    user = await _current_user(x_api_key)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, prefix, label, is_active, created_at, last_used_at
            FROM evo_api_keys WHERE user_id=$1 ORDER BY created_at DESC
        """, user["id"])
    return {"api_keys": [
        {
            "id": str(r["id"]),
            "display": f"{r['prefix']}****",
            "label": r["label"],
            "is_active": r["is_active"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
        } for r in rows
    ]}


@router.post("/me/api-keys")
async def create_api_key(req: CreateApiKeyReq,
                          x_api_key: str = Header(None, alias="X-API-Key")):
    """
    Создаёт новый API-ключ. Сырой ключ отдаётся ОДИН РАЗ в этом ответе —
    сохраняется только его SHA-256-хэш, восстановить ключ из БД нельзя
    (тот же принцип, что у GitHub personal access tokens).
    """
    user = await _current_user(x_api_key)
    raw_key = secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    prefix = raw_key[:8]

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO evo_api_keys (user_id, key_hash, prefix, label)
            VALUES ($1, $2, $3, $4)
            RETURNING id, created_at
        """, user["id"], key_hash, prefix, req.label[:100])

    log.info(f"[Me] Новый API-ключ создан для user={user['id']}, label={req.label}")
    return {
        "id": str(row["id"]),
        "label": req.label,
        "created_at": row["created_at"].isoformat(),
        "api_key": raw_key,
        "warning": "Сохрани этот ключ сейчас — повторно он не показывается.",
    }


@router.delete("/me/api-keys/{key_id}")
async def revoke_api_key(key_id: str,
                          x_api_key: str = Header(None, alias="X-API-Key")):
    """Отзывает свой собственный ключ (не чужой — проверка user_id обязательна)."""
    user = await _current_user(x_api_key)
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE evo_api_keys SET is_active=FALSE WHERE id=$1 AND user_id=$2",
            key_id, user["id"]
        )
    if result.split()[-1] == "0":
        raise HTTPException(404, "Ключ не найден или принадлежит другому пользователю")
    return {"status": "revoked", "id": key_id}


# ── Детальная статистика использования — для графиков личного кабинета ────

@router.get("/me/usage")
async def get_usage_details(x_api_key: str = Header(None, alias="X-API-Key")):
    """
    Ежедневная статистика за последние 30 дней: запросы, латентность,
    токены (реально потрачено ядром vs оценка расхода флагмана без ядра),
    ошибки. Источник — evo_request_log (миграция 009). Не содержит
    содержимого проектов пользователя — только метаданные обращений.
    """
    user = await _current_user(x_api_key)
    pool = await get_pool()
    async with pool.acquire() as conn:
        daily = await conn.fetch("""
            SELECT date_trunc('day', ts) as day,
                   COUNT(*) as requests,
                   AVG(latency_ms)::float as avg_latency_ms,
                   SUM(tokens_actual) as tokens_actual,
                   SUM(tokens_baseline_est) as tokens_baseline_est,
                   COUNT(*) FILTER (WHERE status='error') as errors
            FROM evo_request_log
            WHERE user_id=$1 AND ts > NOW() - INTERVAL '30 days'
            GROUP BY day ORDER BY day ASC
        """, user["id"])
        totals = await conn.fetchrow("""
            SELECT COUNT(*) as requests,
                   AVG(latency_ms)::float as avg_latency_ms,
                   COALESCE(SUM(tokens_actual),0) as tokens_actual,
                   COALESCE(SUM(tokens_baseline_est),0) as tokens_baseline_est,
                   COUNT(*) FILTER (WHERE status='error') as errors
            FROM evo_request_log
            WHERE user_id=$1 AND ts > NOW() - INTERVAL '30 days'
        """, user["id"])
        by_endpoint = await conn.fetch("""
            SELECT endpoint, COUNT(*) as cnt, AVG(latency_ms)::float as avg_latency_ms
            FROM evo_request_log
            WHERE user_id=$1 AND ts > NOW() - INTERVAL '30 days'
            GROUP BY endpoint ORDER BY cnt DESC
        """, user["id"])
        # Честные, проверяемые "киллер"-метрики: доля решений, пришедших
        # 100%-подтверждёнными с первого раза (scenario='full', без
        # партиального/пустого исхода), и насколько независимо решения,
        # которыми пользовался этот аккаунт, подтверждены другими
        # (confirmed_by символа в момент выдачи).
        killer = await conn.fetchrow("""
            SELECT COUNT(*) FILTER (WHERE scenario='full') as full_count,
                   COUNT(*) FILTER (WHERE scenario IS NOT NULL) as scenario_total,
                   AVG(symbol_confirmed_by)::float as avg_confirmed_by,
                   AVG(symbol_rating)::float as avg_rating
            FROM evo_request_log
            WHERE user_id=$1 AND ts > NOW() - INTERVAL '30 days' AND endpoint='/query'
        """, user["id"])
        # Фоновая работа ядра — общая по библиотеке (не привязана к одному
        # user_id, см. миграцию 010), показывается как честный общий вклад,
        # не как выдуманная персональная атрибуция.
        bg = await conn.fetchrow("""
            SELECT COALESCE(SUM(symbols_actualized),0) as symbols_actualized,
                   COALESCE(SUM(ligatures_formed),0) as ligatures_formed,
                   COALESCE(SUM(integrity_fixes),0) as integrity_fixes,
                   COALESCE(SUM(tokens_saved_theoretical),0) as tokens_saved_theoretical
            FROM evo_background_stats WHERE day > NOW() - INTERVAL '30 days'
        """)

    ideal_match_pct = (
        round(100 * killer["full_count"] / killer["scenario_total"], 1)
        if killer["scenario_total"] else None
    )

    tokens_actual = int(totals["tokens_actual"] or 0)
    tokens_baseline = int(totals["tokens_baseline_est"] or 0)
    tokens_saved = max(0, tokens_baseline - tokens_actual)
    saved_pct = round(100 * tokens_saved / tokens_baseline, 1) if tokens_baseline else 0.0

    return {
        "period": "30d",
        "totals": {
            "requests": int(totals["requests"] or 0),
            "avg_latency_ms": round(totals["avg_latency_ms"] or 0, 1),
            "errors": int(totals["errors"] or 0),
            "tokens_actual": tokens_actual,
            "tokens_baseline_est": tokens_baseline,
            "tokens_saved": tokens_saved,
            "tokens_saved_pct": saved_pct,
        },
        "killer_stats": {
            "ideal_match_pct": ideal_match_pct,
            "avg_peer_confirmations": round(killer["avg_confirmed_by"] or 0, 1),
            "avg_solution_rating": round(killer["avg_rating"] or 0, 1),
        },
        "background_work": {
            "note": "Общий вклад фоновой работы ядра по всей библиотеке за 30 дней — не только для вас, но и в вашу пользу как часть общего корпуса решений",
            "symbols_actualized": int(bg["symbols_actualized"] or 0),
            "ligatures_formed": int(bg["ligatures_formed"] or 0),
            "integrity_fixes": int(bg["integrity_fixes"] or 0),
            "tokens_saved_theoretical": int(bg["tokens_saved_theoretical"] or 0),
        },
        "daily": [
            {
                "date": r["day"].date().isoformat(),
                "requests": r["requests"],
                "avg_latency_ms": round(r["avg_latency_ms"] or 0, 1),
                "tokens_actual": int(r["tokens_actual"] or 0),
                "tokens_baseline_est": int(r["tokens_baseline_est"] or 0),
                "errors": r["errors"],
            } for r in daily
        ],
        "by_endpoint": [
            {"endpoint": r["endpoint"], "requests": r["cnt"],
             "avg_latency_ms": round(r["avg_latency_ms"] or 0, 1)}
            for r in by_endpoint
        ],
    }
