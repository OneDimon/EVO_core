"""
Библиотекарь — ювелирный поиск символов и лигатур под план+стек.
Правило: выдаёт наилучшее по (similarity × log(R_f+2)) под конкретный стек.
"""
import logging
from db.pg_client import find_symbols, get_symbol, increment_rating
from db.redis_client import cache_symbol, get_cached_symbol
from shards.shard_client import read_cell, read_cell_local
from core.ai_router import ai_router

log = logging.getLogger("evo.librarian")

async def search(query_text: str, plan_steps: list[str],
                 stack: list[str] = None, session_id: str = "",
                 top_k: int = 5) -> dict:
    """
    Главный поиск: текст + план + стек → набор символов.
    Возвращает: {scenario, symbols, plan_description, cartridge_steps}
    """
    # Векторизация запроса — делает локальная модель ядра
    query_vector = await ai_router.embed(query_text + " " + " ".join(plan_steps))

    # Поиск в pgvector
    symbols = await find_symbols(query_vector, top_k=top_k,
                                  stack_filter=stack, exclude_legacy=True)

    if not symbols:
        return {"scenario": "gap", "symbols": [], "plan_description": "",
                "cartridge_steps": {}}

    # Определяем сценарий
    top_score = symbols[0].get("score", 0) if symbols else 0

    if top_score > 0.92:
        scenario = "full"
    elif top_score > 0.70:
        scenario = "partial"
    else:
        scenario = "gap"

    # Кэшируем горячие символы в Redis
    for s in symbols:
        await cache_symbol(session_id, s['id'], s)

    # Разворачиваем метаданные в человекочитаемый план
    plan_desc = _build_plan_description(symbols, plan_steps)

    # Картридж: шаги без тел (тела раскрываются по step_done)
    cartridge_steps = {}
    for i, step in enumerate(plan_steps, 1):
        if i - 1 < len(symbols):
            cartridge_steps[f"step_{i}"] = {
                "symbol_id": symbols[i-1]['id'],
                "label": symbols[i-1]['label'],
                "description": f"Шаг {i}: {symbols[i-1]['label']}",
                "body_loaded": False
            }

    # N4 fix: кеширование плана убрано из librarian — делается в query.py.
    # Причина: два create_task с одинаковым session_id → race condition.
    # query.py владеет полным контекстом и сохраняет план сам.
    plan_for_redis = [
        {"symbol_id": sym['id'], "label": sym['label'], "step": i+1}
        for i, sym in enumerate(symbols[:len(plan_steps)])
    ]

    return {
        "scenario": scenario,
        "symbols": symbols,
        "plan_description": plan_desc,
        "cartridge_steps": cartridge_steps
    }


async def load_step_body(session_id: str, symbol_id: str) -> dict:
    """
    Загружает тело шага при step_done — декомпрессия zstd.
    Следующий шаг раскрывается только после завершения предыдущего.
    """
    # Сначала Redis горячий кэш
    cached = await get_cached_symbol(session_id, symbol_id)
    sym = cached or await get_symbol(symbol_id)
    if not sym:
        return {"error": f"Symbol {symbol_id} not found"}

    # Декомпрессия тела с шарда
    try:
        if sym.get('shard_host') and sym.get('shard_host') != '':
            content, hyperlinks = await read_cell(
                sym['shard_host'], sym['shard_path'], sym.get('shard_mirror')
            )
        else:
            # Тесты Фазы 0: локальный шард
            content, hyperlinks = await read_cell_local(
                sym.get('shard_path', f"/evo/test/{symbol_id}.zst")
            )
    except Exception as e:
        content = sym.get('label', 'No content available')
        hyperlinks = []
        log.warning(f"Shard read failed for {symbol_id}: {e}")

    # Инкремент рейтинга при вызове
    await increment_rating(symbol_id)

    return {
        "symbol_id": symbol_id,
        "label": sym['label'],
        "content": content,
        "hyperlinks": hyperlinks,
        "applicable_stacks": sym.get('applicable_stacks', []),
        "rating": sym.get('rating_frequency', 0) + 1
    }


def _build_plan_description(symbols: list[dict], plan_steps: list[str]) -> str:
    """Разворачивает метаданные набора в человекочитаемый план."""
    lines = []
    for i, step in enumerate(plan_steps):
        if i < len(symbols):
            sym = symbols[i]
            lines.append(f"Шаг {i+1}: {sym['label']} "
                        f"[{sym['science']} / {sym['section']} / {sym['subsection']}]")
        else:
            lines.append(f"Шаг {i+1}: {step} — поиск решения")
    return "\n".join(lines)
