"""POST /api/v1/query — главный поиск: план+стек → картридж."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from core.librarian import search

router = APIRouter()

class QueryRequest(BaseModel):
    session_id: str
    user_request: str
    flagship_plan: list[str] = []
    context: Optional[dict] = None

@router.post("/query")
async def query(req: QueryRequest):
    stack = (req.context or {}).get("detected_stack", [])

    result = await search(
        query_text=req.user_request,
        plan_steps=req.flagship_plan,
        stack=stack,
        session_id=req.session_id
    )

    scenario = result["scenario"]

    if scenario == "full":
        return {
            "status": "cartridge_ready",
            "scenario": "full",
            "plan_description": result["plan_description"],
            "instructions": result["cartridge_steps"],
            "rating": result["symbols"][0].get("rating_frequency", 0) if result["symbols"] else 0
        }
    elif scenario == "partial":
        return {
            "status": "cartridge_partial",
            "scenario": "partial",
            "plan_description": result["plan_description"],
            "partial_instructions": result["cartridge_steps"],
            "directive": (
                "Смежный базис выдан. Адаптируй под свои вводные. "
                "Протестируй в песочнице. Отчитайся."
            )
        }
    else:
        return {
            "status": "cartridge_empty",
            "scenario": "gap",
            "directive": (
                "В базе нет решения. Найди во внешних источниках: "
                "GitHub (высокорейтинговые), официальная документация, "
                "маркетплейсы скиллов. Протестируй до зелёных статусов. Отчитайся."
            )
        }
