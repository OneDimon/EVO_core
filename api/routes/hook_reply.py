"""POST /api/v1/hook_reply — ответ флагмана на хук-допрос."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class HookReplyRequest(BaseModel):
    session_id: str
    has_update: bool
    update_description: Optional[str] = None
    compatible_with_current_stack: bool = True
    migration_scope: str = "none"  # "none" | "partial" | "full"

@router.post("/hook_reply")
async def hook_reply(req: HookReplyRequest):
    if not req.has_update:
        return {"status": "session_complete", "message": "База знаний актуальна."}

    return {
        "status": "update_recorded",
        "message": f"Обновление зафиксировано: {req.update_description}",
        "migration_scope": req.migration_scope,
        "next_action": (
            "prepare_migration_plan"
            if req.migration_scope in ["partial", "full"]
            else "knowledge_updated"
        )
    }
