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


# ── Сводная статистика ядра — для админ-панели ────────────────────────────────

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
