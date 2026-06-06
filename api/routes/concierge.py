"""POST /api/v1/concierge — консьерж-диалог (незаметно для пользователя)."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from core.ai_router import ai_router

router = APIRouter()

class ConciergeRequest(BaseModel):
    session_id: str
    user_request: str
    concierge_answers: Optional[dict] = None

@router.post("/concierge")
async def concierge(req: ConciergeRequest):
    if not req.concierge_answers:
        # Фаза 1: генерируем вопросы через AI Router
        questions = await ai_router.generate(req.user_request, "concierge")
        return {
            "status": "concierge_questions",
            "questions": questions.split("\n")[:3]
        }
    # Принимаем ответы флагмана
    return {
        "status": "context_accepted",
        "proceed": True,
        "detected_stack": req.concierge_answers.get("detected_stack", []),
        "project_type": req.concierge_answers.get("project_type", "unknown")
    }
