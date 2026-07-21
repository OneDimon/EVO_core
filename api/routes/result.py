"""
POST /api/v1/result — отчёт флагмана.
Фаза 1: подключён YMS-MMM verifier + контур Obsidian.
"""
import asyncio, logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from core.verifier import VerifyRequest, verify
from core.obsidian import process as obsidian_process, generate_hook_query

log = logging.getLogger("evo.result")
router = APIRouter()

class ResultRequest(BaseModel):
    session_id: str
    status: str
    result: str
    steps_completed: list[int] = []
    workability_confirmed: bool
    workability_proof: str = ""
    solution_quality: str        # "ideal" | "adapted" | "gap_filled"
    deviations: Optional[str] = None
    applied_stack: list[str] = []
    original_tz: str             # P9 fix: ОБЯЗАТЕЛЬНОЕ поле. Без него YMS-MMM
                                 # верифицирует вывод против самого себя → всегда pass.
                                 # Флагман ОБЯЗАН передавать оригинальное ТЗ пользователя.
    cartridge: Optional[dict] = None
    notes: Optional[str] = None

@router.post("/result")
async def result(req: ResultRequest):
    vreq = VerifyRequest(
        session_id=req.session_id,
        output=req.result,
        original_tz=req.original_tz,  # P9: теперь обязательное поле
        cartridge=req.cartridge or {},
        applied_stack=req.applied_stack,
        solution_quality=req.solution_quality,
        deviations=req.deviations,
        workability_confirmed=req.workability_confirmed,
        workability_proof=req.workability_proof,
    )

    vresult = await verify(vreq)

    if not vresult.passed:
        if vresult.action == "reanimate":
            # БЛОК 07: Immune System
            from core.immune_system import reanimate
            asyncio.create_task(reanimate(
                session_id=req.session_id,
                task_description=req.original_tz,
                base_instructions=str(req.cartridge or {}),
                faulty_output=req.result,
                error_log="; ".join(vresult.failures),
                callback_url="/api/v1/patch_callback"
            ))
            return {
                "status": "reanimate",
                "message": "Реаниматор активирован. Патч будет готов через /api/v1/patch_callback",
                "failures": vresult.failures
            }
        return {
            "status": "failed",
            "reason": "; ".join(vresult.failures),
            "fix_directive": vresult.fix_directive
        }

    # Запускаем Obsidian асинхронно — пользователь не ждёт
    asyncio.create_task(obsidian_process(
        verify_result=vresult,
        session_id=req.session_id,
        output=req.result,
        original_tz=req.original_tz,  # P9: теперь обязательное поле
        applied_stack=req.applied_stack,
        cartridge=req.cartridge or {},
        deviations=req.deviations or "",
    ))

    hook = await generate_hook_query(req.applied_stack)
    return {
        "status": "verified",
        "action": vresult.action,
        "score": vresult.score,
        "delta_type": vresult.delta_type,
        "message": "Результат верифицирован. Передай пользователю.",
        "hook_query": hook
    }
