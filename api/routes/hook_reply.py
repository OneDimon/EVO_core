"""POST /api/v1/hook_reply — ответ флагмана на хук-допрос."""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.signature import verify_request, sign_response

log = logging.getLogger("evo.hook_reply")
router = APIRouter()

class HookReplyRequest(BaseModel):
    session_id: str
    has_update: bool
    update_description: Optional[str] = None
    compatible_with_current_stack: bool = True
    migration_scope: str = "none"  # "none" | "partial" | "full"
    applied_stack: list[str] = []  # N6 fix: нужен для archive()
    evo_signature: Optional[str] = None

@router.post("/hook_reply")
async def hook_reply(req: HookReplyRequest):
    if not await verify_request(req.model_dump(), req.session_id):
        raise HTTPException(401, "invalid_evo_signature")

    if not req.has_update:
        # Флагман подтвердил: решение из картриджа всё ещё актуально
        # относительно текущих технологий (ШАГ 7 FLAGSHIP_SYSTEM_PROMPT.md —
        # обязательная проверка). Сбрасываем last_tech_check — следующая
        # обязательная проверка (query.py::tech_check_required) снова
        # наступит не раньше чем через TECH_CHECK_STALE_DAYS (30 дней).
        # Без этого сброса символ вечно считался бы "устаревшим" даже
        # сразу после успешной проверки.
        from db.redis_client import get_session_plan
        from db.pg_client import get_pool
        plan = await get_session_plan(req.session_id)
        if plan:
            symbol_ids = [step.get("symbol_id") for step in plan if step.get("symbol_id")]
            if symbol_ids:
                pool = await get_pool()
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE scl_symbols SET last_tech_check = NOW() "
                        "WHERE id = ANY($1::text[])",
                        symbol_ids
                    )
                log.info(f"[HookReply] Актуальность подтверждена, "
                         f"last_tech_check обновлён: {symbol_ids}")
        return await sign_response(
            {"status": "session_complete", "message": "База знаний актуальна."},
            req.session_id
        )

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

    return await sign_response({
        "status": "update_recorded",
        "message": f"Обновление зафиксировано и отправлено в archivist: {req.update_description}",
        "migration_scope": req.migration_scope,
        "next_action": (
            "prepare_migration_plan"
            if req.migration_scope in ["partial", "full"]
            else "knowledge_updated"
        )
    }, req.session_id)
