"""POST /api/v1/step_done — шаг N завершён, выдать шаг N+1."""
from fastapi import APIRouter
from pydantic import BaseModel
from db.redis_client import get_session_plan
from core.librarian import load_step_body

router = APIRouter()

class StepDoneRequest(BaseModel):
    session_id: str
    step_completed: int
    step_result: str = "success"
    next_step_requested: int

@router.post("/step_done")
async def step_done(req: StepDoneRequest):
    plan = await get_session_plan(req.session_id)
    if not plan:
        return {"status": "error", "message": "Session plan not found"}

    next_idx = req.next_step_requested - 1
    if next_idx >= len(plan):
        return {"status": "plan_complete", "message": "All steps completed"}

    next_step = plan[next_idx]
    # Декомпрессия тела следующего символа — только сейчас
    body = await load_step_body(req.session_id, next_step["symbol_id"])

    return {
        "status": "next_step_ready",
        "step": req.next_step_requested,
        "symbol_id": next_step["symbol_id"],
        "instruction": body.get("content", ""),
        "hyperlinks": body.get("hyperlinks", []),
        "label": body.get("label", "")
    }
