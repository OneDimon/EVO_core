"""POST /api/v1/query — главный поиск: план+стек → картридж."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.librarian import search
from core.signature import verify_request, sign_response

router = APIRouter()

class QueryRequest(BaseModel):
    session_id: str
    user_request: str
    flagship_plan: list[str] = []
    context: Optional[dict] = None
    evo_signature: Optional[str] = None

@router.post("/query")
async def query(req: QueryRequest):
    if not await verify_request(req.model_dump(), req.session_id):
        raise HTTPException(401, "invalid_evo_signature")

    stack = (req.context or {}).get("detected_stack", [])

    result = await search(
        query_text=req.user_request,
        plan_steps=req.flagship_plan,
        stack=stack,
        session_id=req.session_id
    )

    scenario = result["scenario"]

    # Сохранить план в Redis — step_done читает отсюда
    if result.get("symbols"):
        from db.redis_client import cache_session_plan
        plan_data = [
            {"symbol_id": s['id'], "label": s['label'], "step": i+1}
            for i, s in enumerate(result["symbols"][:len(req.flagship_plan)])
        ]
        import asyncio
        asyncio.create_task(cache_session_plan(req.session_id, plan_data))

    # Сигнал давности знания — обязывает флагмана к проверке актуальности
    # (ШАГ 7 хук-допрос в FLAGSHIP_SYSTEM_PROMPT.md) не только для новых
    # решений, но и для СТАРЫХ переиспользуемых картриджей. Без этого
    # символ мог бы использоваться годами без единой проверки на устаревание,
    # хотя правило "хук-допрос обязателен" (БЛОК 5 п.12) формально не нарушается.
    TECH_CHECK_STALE_DAYS = 30
    tech_check_required = False
    days_since_verified = None
    if result.get("symbols"):
        from datetime import datetime, timezone
        top = result["symbols"][0]
        last_check = top.get("last_tech_check")
        if last_check:
            if last_check.tzinfo is None:
                last_check = last_check.replace(tzinfo=timezone.utc)
            days_since_verified = (datetime.now(timezone.utc) - last_check).days
            tech_check_required = days_since_verified >= TECH_CHECK_STALE_DAYS

    if scenario == "full":
        return await sign_response({
            "status": "cartridge_ready",
            "scenario": "full",
            "plan_description": result["plan_description"],
            "instructions": result["cartridge_steps"],
            "rating": result["symbols"][0].get("rating_frequency", 0) if result["symbols"] else 0,
            "tech_check_required": tech_check_required,
            "days_since_verified": days_since_verified,
        }, req.session_id)
    elif scenario == "partial":
        return await sign_response({
            "status": "cartridge_partial",
            "scenario": "partial",
            "plan_description": result["plan_description"],
            "partial_instructions": result["cartridge_steps"],
            "directive": (
                "Смежный базис выдан. Адаптируй под свои вводные. "
                "Протестируй в песочнице. Отчитайся."
            ),
            "tech_check_required": tech_check_required,
            "days_since_verified": days_since_verified,
        }, req.session_id)
    else:
        return await sign_response({
            "status": "cartridge_empty",
            "scenario": "gap",
            "directive": (
                "В базе нет решения. Найди во внешних источниках: "
                "GitHub (высокорейтинговые), официальная документация, "
                "маркетплейсы скиллов. Протестируй до зелёных статусов. Отчитайся."
            )
        }, req.session_id)
