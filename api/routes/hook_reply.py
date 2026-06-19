"""POST /api/v1/hook_reply — ответ флагмана на хук-допрос."""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

log = logging.getLogger("evo.hook_reply")
router = APIRouter()

class HookReplyRequest(BaseModel):
    session_id: str
    has_update: bool
    update_description: Optional[str] = None
    compatible_with_current_stack: bool = True
    migration_scope: str = "none"  # "none" | "partial" | "full"
    applied_stack: list[str] = []  # N6 fix: нужен для archive()

@router.post("/hook_reply")
async def hook_reply(req: HookReplyRequest):
    if not req.has_update:
        return {"status": "session_complete", "message": "База знаний актуальна."}

    # N6 fix: ранее update_description только логировался в ответ
    # и никогда не попадал в archivist — обновление терялось.
    if not req.update_description:
        raise HTTPException(
            status_code=422,
            detail="has_update=True требует update_description"
        )

    from core.archivist import archive
    await archive(
        session_id=req.session_id,
        output=req.update_description,
        solution_quality="gap_filled",
        deviations="",
        applied_stack=req.applied_stack,
        original_tz=f"hook-update: {req.update_description[:150]}",
        context={"source": "hook_reply", "migration_scope": req.migration_scope}
    )
    log.info(f"[HookReply] Обновление поставлено в archivist: {req.session_id}")

    return {
        "status": "update_recorded",
        "message": f"Обновление зафиксировано и отправлено в archivist: {req.update_description}",
        "migration_scope": req.migration_scope,
        "next_action": (
            "prepare_migration_plan"
            if req.migration_scope in ["partial", "full"]
            else "knowledge_updated"
        )
    }
