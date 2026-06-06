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
    secret = os.getenv("EVO_API_SECRET", "dev_admin_secret")
    if token != secret:
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
