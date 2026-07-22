"""
Immune System — БЛОК 07, Фаза 2

Реаниматор: 3 провала YMS-MMM → патч через AI Router (Gemini → Gemini Flash
fallback → Ollama local, цепочка задаётся в config/ai_router.json, см.
core/ai_router.py::AIRouter._call_with_fallback) → патч флагману через
GET /api/v1/patch_callback.

Полностью in-process: реаниматор не зависит ни от какой внешней очереди или
воркфлоу-движка — весь цикл (генерация патча, хранение, выдача) выполняется
кодом этого модуля и core/ai_router.py. (Историческая заметка: до этого
аудита в репозитории лежал параллельный n8n-воркфлоу, дублировавший ровно
эту логику снаружи процесса — он никогда не был частью реального пути
вызова result.py→reanimate() и удалён как избыточная инфраструктура, см.
n8n/MIGRATED_TO_CODE.md.)

Правила: BLOCK_07_immune_system.md, LOCAL_MODEL_INSTRUCTIONS.md
"""
import logging
from core.ai_router import ai_router
from db.redis_client import get_redis

log = logging.getLogger("evo.immune")


async def reanimate(session_id: str, task_description: str,
                    base_instructions: str, faulty_output: str,
                    error_log: str, callback_url: str = "") -> dict:
    """
    Точка входа реаниматора.
    Вызывается из result.py при action="reanimate" (через asyncio.create_task
    — результат не возвращается вызывающему напрямую, поэтому любая ошибка
    здесь ОБЯЗАНА быть перехвачена и записана в Redis явным статусом, иначе
    она тихо теряется в fire-and-forget таске, а флагман, опрашивающий
    /patch_callback, увидит неотличимое от "ещё не готово" отсутствие патча
    (см. patch_callback ниже — статус "failed" сделан отдельным от "не найден").
    """
    r = await get_redis()
    prompt = (
        f"[EVO-CORE IMMUNE SYSTEM]\n"
        f"TASK: {task_description[:400]}\n"
        f"BASE_INSTRUCTIONS: {base_instructions[:400]}\n"
        f"FAULTY_OUTPUT: {faulty_output[:400]}\n"
        f"ERROR_LOG: {error_log[:300]}\n\n"
        "Find the EXACT point of failure. "
        "Return a zero-fluff surgical code patch ONLY. No explanations."
    )

    try:
        patch = await ai_router.generate(prompt, task="immune_patch")
    except Exception as e:
        # Все провайдеры цепочки (primary + fallback_chain) исчерпаны —
        # громко фиксируем явный отказ вместо тихой потери в create_task.
        log.error(f"[Immune] Реанимация провалена для {session_id}: {e}")
        await r.setex(f"evo:patch:{session_id}", 3600, "__FAILED__:" + str(e)[:200])
        return {"status": "failed", "session_id": session_id, "error": str(e)}

    # Сохранить патч в Redis для callback
    await r.setex(f"evo:patch:{session_id}", 3600, patch)
    log.info(f"[Immune] Патч сгенерирован для {session_id}")

    return {"status": "reanimated", "patch": patch, "session_id": session_id}


async def patch_callback(session_id: str) -> dict:
    """
    Отдаёт сохранённый патч флагману. Три различимых исхода:
      - "reanimated" + patch  — патч готов
      - "failed"              — реанимация завершилась ошибкой (все
                                 AI-провайдеры недоступны), см. reanimate()
      - "pending"              — патч ещё не готов, либо TTL (1 час) истёк,
                                 либо неверный session_id
    """
    r = await get_redis()
    patch = await r.get(f"evo:patch:{session_id}")
    if not patch:
        return {"status": "pending", "session_id": session_id,
                "message": "Патч не найден: ещё не готов, истёк TTL (1ч) "
                           "или неверный session_id"}
    patch = patch.decode()
    if patch.startswith("__FAILED__:"):
        return {"status": "failed", "session_id": session_id,
                "error": patch[len("__FAILED__:"):]}
    return {"status": "reanimated", "session_id": session_id, "patch": patch}
