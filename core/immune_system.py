"""
Immune System — БЛОК 07, Фаза 2
Реаниматор: 3 провала YMS-MMM → Gemini → Ollama fallback → патч флагману.
Правила: BLOCK_07_immune_system.md, LOCAL_MODEL_INSTRUCTIONS.md
"""
import logging, asyncio
from core.ai_router import ai_router
from db.redis_client import get_redis

log = logging.getLogger("evo.immune")


async def reanimate(session_id: str, task_description: str,
                    base_instructions: str, faulty_output: str,
                    error_log: str, callback_url: str = "") -> dict:
    """
    Точка входа реаниматора.
    Вызывается из result.py при action="reanimate".
    Генерирует хирургический патч через AI Router.
    """
    prompt = (
        f"[EVO-CORE IMMUNE SYSTEM]\n"
        f"TASK: {task_description[:400]}\n"
        f"BASE_INSTRUCTIONS: {base_instructions[:400]}\n"
        f"FAULTY_OUTPUT: {faulty_output[:400]}\n"
        f"ERROR_LOG: {error_log[:300]}\n\n"
        "Find the EXACT point of failure. "
        "Return a zero-fluff surgical code patch ONLY. No explanations."
    )

    patch = await ai_router.generate(prompt, task="immune_patch")

    # Сохранить патч в Redis для callback
    r = await get_redis()
    await r.setex(f"evo:patch:{session_id}", 3600, patch)
    log.info(f"[Immune] Патч сгенерирован для {session_id}")

    return {"status": "reanimated", "patch": patch, "session_id": session_id}


async def patch_callback(session_id: str) -> dict:
    """Отдаёт сохранённый патч флагману."""
    r = await get_redis()
    patch = await r.get(f"evo:patch:{session_id}")
    if not patch:
        return {"status": "error", "message": "Патч не найден или истёк"}
    return {"status": "reanimated", "patch": patch.decode()}
