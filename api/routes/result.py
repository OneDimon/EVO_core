"""POST /api/v1/result — отчёт флагмана о выполнении."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from core.archivist import archive

router = APIRouter()

class ResultRequest(BaseModel):
    session_id: str
    status: str
    result: str
    steps_completed: list[int] = []
    workability_confirmed: bool
    workability_proof: str = ""
    solution_quality: str   # "ideal" | "adapted" | "gap_filled"
    deviations: Optional[str] = None
    applied_stack: list[str] = []
    notes: Optional[str] = None

@router.post("/result")
async def result(req: ResultRequest):
    if not req.workability_confirmed:
        return {
            "status": "failed",
            "reason": "workability_confirmed = false",
            "fix_directive": (
                "Проверь работоспособность. Не код — реальный запуск. "
                "Нужен 200 OK / зелёные тесты / успешный старт сервиса."
            )
        }

    # Запускаем архивацию асинхронно — пользователь не ждёт
    await archive(
        session_id=req.session_id,
        output=req.result,
        solution_quality=req.solution_quality,
        deviations=req.deviations or "",
        applied_stack=req.applied_stack,
        original_tz=req.result[:200],
        context={}
    )

    return {
        "status": "verified",
        "action": {
            "ideal": "record_confirmation",
            "adapted": "analyze_delta",
            "gap_filled": "record_new_knowledge"
        }.get(req.solution_quality, "record_confirmation"),
        "message": "Результат верифицирован. Передай пользователю.",
        "hook_query": "...или есть что-то ещё новее по этой теме?"
    }
