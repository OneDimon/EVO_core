"""POST /api/v1/step_done — шаг N завершён, выдать шаг N+1."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.redis_client import get_session_plan
from core.librarian import load_step_body
from core.signature import verify_request, sign_response

router = APIRouter()

class StepDoneRequest(BaseModel):
    session_id: str
    step_completed: int
    step_result: str = "success"
    next_step_requested: int
    evo_signature: Optional[str] = None

@router.post("/step_done")
async def step_done(req: StepDoneRequest):
    if not await verify_request(req.model_dump(), req.session_id):
        raise HTTPException(401, "invalid_evo_signature")

    plan = await get_session_plan(req.session_id)
    if not plan:
        return await sign_response(
            {"status": "error", "message": "Session plan not found"},
            req.session_id
        )

    # fix: next_step_requested=0 (или отрицательное) давал next_idx<0 —
    # Python возвращает plan[-1] (ПОСЛЕДНИЙ шаг) вместо ошибки при
    # отрицательной индексации. Валидация нижней границы обязательна.
    if req.next_step_requested < 1:
        return await sign_response(
            {"status": "error", "message": "next_step_requested должен быть >= 1"},
            req.session_id
        )
    next_idx = req.next_step_requested - 1
    if next_idx >= len(plan):
        return await sign_response(
            {"status": "plan_complete", "message": "All steps completed"},
            req.session_id
        )

    next_step = plan[next_idx]
    # Декомпрессия тела следующего символа — только сейчас
    body = await load_step_body(req.session_id, next_step["symbol_id"])

    return await sign_response({
        "status": "next_step_ready",
        "step": req.next_step_requested,
        "symbol_id": next_step["symbol_id"],
        "instruction": body.get("content", ""),
        "hyperlinks": body.get("hyperlinks", []),
        "label": body.get("label", "")
    }, req.session_id)
