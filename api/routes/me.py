"""
GET /api/v1/me — личный кабинет пользователя.
Возвращает данные аккаунта и статистику использования по собственному API-ключу.
Связан с: db/users.py (evo_users), db/migrations/003_users_security.sql (evo_rate_stats).
"""
import logging
from fastapi import APIRouter, Header, HTTPException
from db.pg_client import get_pool

log = logging.getLogger("evo.me")
router = APIRouter()

PLAN_LIMITS = {
    "free": {"requests_per_month": 5000, "shards_visible": 1},
    "pro": {"requests_per_month": 50000, "shards_visible": 3},
    "enterprise": {"requests_per_month": None, "shards_visible": None},
}

@router.get("/me")
async def get_me(x_api_key: str = Header(None, alias="X-API-Key")):
    """Личный кабинет: профиль + использование за текущий месяц."""
    if not x_api_key:
        raise HTTPException(401, "Требуется X-API-Key")

    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, email, plan, is_active, created_at, last_seen "
            "FROM evo_users WHERE api_key=$1",
            x_api_key
        )
        if not user or not user["is_active"]:
            raise HTTPException(403, "Недействительный или отключённый ключ")

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
        "api_key_masked": x_api_key[:8] + "****" + x_api_key[-4:],
    }
