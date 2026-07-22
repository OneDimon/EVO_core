"""POST /api/v1/concierge — консьерж-диалог (незаметно для пользователя)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.ai_router import ai_router
from core.signature import verify_request, sign_response

router = APIRouter()

class ConciergeRequest(BaseModel):
    session_id: str
    user_request: str
    concierge_answers: Optional[dict] = None
    evo_signature: Optional[str] = None

@router.post("/concierge")
async def concierge(req: ConciergeRequest):
    if not await verify_request(req.model_dump(), req.session_id):
        raise HTTPException(401, "invalid_evo_signature")

    if not req.concierge_answers:
        # Фаза 1: генерируем вопросы через AI Router
        # fix: "concierge" не совпадал с ключом routing_rules "concierge_questions"
        # (тот же паттерн бага что был у immune_system_patch/immune_patch, Урок 1)
        questions = await ai_router.generate(req.user_request, "concierge_questions")
        return await sign_response({
            "status": "concierge_questions",
            "questions": questions.split("\n")[:3]
        }, req.session_id)
    # Принимаем ответы флагмана
    return await sign_response({
        "status": "context_accepted",
        "proceed": True,
        "detected_stack": req.concierge_answers.get("detected_stack", []),
        "project_type": req.concierge_answers.get("project_type", "unknown")
    }, req.session_id)
