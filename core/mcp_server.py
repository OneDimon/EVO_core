"""
MCP Server — БЛОК 05, Фаза 2
JSON-RPC 2.0 шлюз для исполнения команд во внешних средах.
Протокол: Streamable HTTP + JSON-RPC 2.0.
Среды: n8n, ZennoPoster, Google Sheets, внешние API.
Правила: BLOCK_05_mcp_server.md
"""
import logging, json, uuid
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

log = logging.getLogger("evo.mcp")
router = APIRouter()


class JsonRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[dict] = None
    id: Optional[str] = None


class JsonRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[dict] = None
    id: Optional[str] = None


# Реестр доступных методов (среды исполнения)
_HANDLERS = {}

def mcp_method(name: str):
    """Декоратор для регистрации MCP методов."""
    def decorator(fn):
        _HANDLERS[name] = fn
        return fn
    return decorator


@router.post("/mcp")
async def mcp_endpoint(req: JsonRPCRequest):
    """Streamable HTTP JSON-RPC 2.0 точка входа."""
    handler = _HANDLERS.get(req.method)
    if not handler:
        return JsonRPCResponse(
            id=req.id,
            error={"code": -32601, "message": f"Method not found: {req.method}"}
        )
    try:
        result = await handler(req.params or {})
        return JsonRPCResponse(id=req.id, result=result)
    except Exception as e:
        log.error(f"[MCP] {req.method} error: {e}")
        return JsonRPCResponse(
            id=req.id,
            error={"code": -32000, "message": str(e)}
        )


# ── Методы исполнения ────────────────────────────────────────────────────────

@mcp_method("n8n.trigger_workflow")
async def n8n_trigger(params: dict) -> dict:
    """Запустить n8n воркфлоу через webhook."""
    import httpx
    from core.config_manager import get
    base_url = await get("N8N_BASE_URL", "http://localhost:5678")
    webhook_path = params.get("webhook_path", "")
    payload = params.get("payload", {})
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{base_url}/webhook/{webhook_path}", json=payload)
        return {"status": r.status_code, "response": r.json() if r.content else {}}


@mcp_method("sheets.append_row")
async def sheets_append(params: dict) -> dict:
    """Добавить строку в Google Sheets."""
    from core.config_manager import get
    import httpx
    token = await get("SHARD_GDRIVE_TOKEN")
    spreadsheet_id = params.get("spreadsheet_id")
    range_ = params.get("range", "Sheet1!A1")
    values = params.get("values", [])
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_}:append",
            params={"valueInputOption": "RAW"},
            headers={"Authorization": f"Bearer {token}"},
            json={"values": [values]}
        )
        return {"status": r.status_code}


@mcp_method("evo.query")
async def evo_query(params: dict) -> dict:
    """Прямой запрос к ядру EVO через MCP."""
    from core.librarian import search
    result = await search(
        query_text=params.get("user_request", ""),
        plan_steps=params.get("flagship_plan", []),
        stack=params.get("stack", []),
        session_id=params.get("session_id", str(uuid.uuid4()))
    )
    return result


@mcp_method("system.list_methods")
async def list_methods(params: dict) -> dict:
    """Список доступных MCP методов."""
    return {"methods": list(_HANDLERS.keys())}
