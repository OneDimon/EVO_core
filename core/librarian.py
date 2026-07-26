"""
Библиотекарь — ювелирный поиск символов и лигатур под план+стек.
Правило: выдаёт наилучшее по (similarity × log(R_f+2)) под конкретный стек.
"""
import re
import logging
from db.pg_client import find_symbols, get_symbol, increment_rating
from db.redis_client import (
    cache_symbol, get_cached_symbol,
    cache_embedding, get_cached_embedding,
)
from shards.shard_client import read_cell, read_cell_local
from shards.zstd_codec import parse_hyperlinks
from core.ai_router import ai_router

log = logging.getLogger("evo.librarian")

MAX_HYPERLINK_DEPTH = 3  # предел фрактального разворачивания гиперлинков

LIGATURE_MATCH_THRESHOLD = 0.85  # ниже порога "full" (0.92), чтобы не
# отсеивать уверенное совпадение целой методички под комбинированный текст
# плана (он длиннее и "шумнее" одного шага, чуть ниже similarity — это
# ожидаемо), но выше порога "partial" (0.70) — это не намёк, а версия

STEP_MATCH_FULL = 0.92
STEP_MATCH_PARTIAL = 0.70


async def search(query_text: str, plan_steps: list[str],
                 stack: list[str] = None, session_id: str = "",
                 top_k: int = 5) -> dict:
    """
    Главный поиск: текст + план + стек → набор символов.
    Возвращает: {scenario, symbols, plan_description, cartridge_steps,
                 plan_for_redis, assembly_mode}

    Порядок поиска (см. LOCAL_MODEL_INSTRUCTIONS.md — пример SSH+WARP):
    1. Сначала — цельная лигатура под ВЕСЬ сценарий целиком. Если план уже
       был решён и подтверждён как одна цепочка, она несёт знание про
       порядок и побочные эффекты шагов (кто-то реально это прогнал
       end-to-end и подтвердил), которого у независимо найденных "лучших
       по смыслу" символов для каждого шага в отдельности нет и не может
       быть. Её собственные вшитые гиперлинки (core/librarian.py::
       _resolve_hyperlinks) сами разворачиваются в верном порядке при
       выдаче тела — отдельно проверять последовательность не нужно, она
       уже зашита в подтверждённый контент.
    2. Если цельного подтверждённого сценария нет — сборка по шагам, но
       КАЖДЫЙ шаг ищется НЕЗАВИСИМО (свой эмбеддинг, свой порог), не
       позиционным зипом top-K по одному общему вектору всего плана —
       иначе шаг №2 может получить символ, реально близкий по смыслу к
       шагу №4, просто потому что оказался вторым в списке похожести.
       В этом режиме порядок/побочные эффекты НЕ проверены ядром
       автоматически — assembly_mode="per_step" сигналит query.py добавить
       флагману явную директиву проверить это самому.
    """
    embed_key = query_text + " " + " ".join(plan_steps)

    # ── ШАГ 1: цельная лигатура под весь сценарий ───────────────────────
    query_vector = await get_cached_embedding(embed_key)
    if query_vector is None:
        query_vector = await ai_router.embed(embed_key)
        await cache_embedding(embed_key, query_vector)

    candidates = await find_symbols(query_vector, top_k=max(top_k, 10),
                                     stack_filter=stack, exclude_legacy=True)
    ligature_match = next(
        (s for s in candidates
         if '⊕' in s['id'] and s.get('score', 0) >= LIGATURE_MATCH_THRESHOLD),
        None
    )

    if ligature_match:
        await cache_symbol(session_id, ligature_match['id'], ligature_match)
        plan_desc = (
            f"Найдена подтверждённая методичка целиком под задачу: "
            f"{ligature_match['label']} [{ligature_match.get('science','')} / "
            f"{ligature_match.get('section','')}]"
        )
        return {
            "scenario": "full",
            "symbols": [ligature_match],
            "plan_description": plan_desc,
            "cartridge_steps": {
                "step_1": {
                    "label": ligature_match['label'],
                    "description": plan_desc,
                    "body_loaded": False
                }
            },
            "plan_for_redis": [
                {"symbol_id": ligature_match['id'], "label": ligature_match['label'], "step": 1}
            ],
            "assembly_mode": "ligature",
        }

    # ── ШАГ 2: нет цельного сценария — независимый поиск по каждому шагу ─
    if not plan_steps:
        # план не разбит на шаги (или пуст) — деградация к старому
        # поведению одним общим top-1 по объединённому вектору
        plan_steps = [query_text]

    symbols = []
    plan_for_redis = []
    for i, step_text in enumerate(plan_steps, 1):
        step_key = step_text
        step_vector = await get_cached_embedding(step_key)
        if step_vector is None:
            step_vector = await ai_router.embed(step_key)
            await cache_embedding(step_key, step_vector)

        step_result = await find_symbols(step_vector, top_k=1,
                                          stack_filter=stack, exclude_legacy=True)
        if not step_result:
            continue
        sym = step_result[0]
        symbols.append(sym)
        await cache_symbol(session_id, sym['id'], sym)
        plan_for_redis.append({"symbol_id": sym['id'], "label": sym['label'], "step": i})

    if not symbols:
        return {"scenario": "gap", "symbols": [], "plan_description": "",
                "cartridge_steps": {}, "plan_for_redis": [], "assembly_mode": "per_step"}

    scores = [s.get("score", 0) for s in symbols]
    if len(symbols) == len(plan_steps) and min(scores) > STEP_MATCH_FULL:
        scenario = "full"
    elif max(scores) > STEP_MATCH_PARTIAL:
        scenario = "partial"
    else:
        scenario = "gap"

    plan_desc = _build_plan_description(symbols, plan_steps)

    cartridge_steps = {}
    for i, sym in enumerate(symbols, 1):
        cartridge_steps[f"step_{i}"] = {
            "label": sym['label'],
            "description": f"Шаг {i}: {sym['label']}",
            "body_loaded": False
        }

    return {
        "scenario": scenario,
        "symbols": symbols,
        "plan_description": plan_desc,
        "cartridge_steps": cartridge_steps,
        "plan_for_redis": plan_for_redis,
        "assembly_mode": "per_step",
    }


async def _resolve_hyperlinks(content: str, depth: int = 0, visited: set = None) -> str:
    """
    Разворачивает [[EVO:symbol_id | описание]] прямо в тексте инструкции —
    подставляет реальное содержимое связанного символа рекурсивно, вместо
    того чтобы отдавать сырую внутреннюю нотацию наружу флагману.

    Правило Архитектора: символы/лигатуры — исключительно внутренний язык
    ядра. Но сам гиперлинк внутри ячейки — не мусор для вычистки, а рабочий
    механизм фрактального раскрытия (лигатура → символы → более частные
    ячейки → и так вглубь, без дублирования контента между ячейками) —
    поэтому не просто удаляем ссылку, а РАЗВОРАЧИВАЕМ её в реальный текст.

    depth/visited защищают от чрезмерной/циклической рекурсии:
    MAX_HYPERLINK_DEPTH ограничивает глубину, visited — множество уже
    раскрытых id в этой цепочке, чтобы A→B→A не зациклилось.
    """
    if visited is None:
        visited = set()

    links = parse_hyperlinks(content)
    if not links:
        return content

    resolved = content
    for link in links:
        sub_id = link["symbol_id"]
        fallback = link["description"] or "[смежное решение]"

        if depth >= MAX_HYPERLINK_DEPTH or sub_id in visited:
            # Предел глубины или цикл — безопасный откат на человекочитаемое
            # описание без внутреннего адреса (не сырая нотация, но и не
            # обрыв: флагман видит осмысленный текст, а не мусор/адрес).
            replacement = fallback
        else:
            visited.add(sub_id)
            sub_sym = await get_symbol(sub_id)
            if not sub_sym:
                replacement = fallback
            else:
                try:
                    if sub_sym.get('shard_host'):
                        sub_content, _ = await read_cell(
                            sub_sym['shard_host'], sub_sym['shard_path'],
                            sub_sym.get('shard_mirror')
                        )
                    else:
                        sub_content, _ = await read_cell_local(
                            sub_sym.get('shard_path', f"/evo/test/{sub_id}.zst")
                        )
                    sub_content = await _resolve_hyperlinks(sub_content, depth + 1, visited)
                    await increment_rating(sub_id)
                    label = sub_sym.get('label', fallback)
                    replacement = f"\n--- [{label}] ---\n{sub_content}\n--- конец ---\n"
                except Exception as e:
                    log.warning(f"[Librarian] Не удалось раскрыть гиперлинк {sub_id}: {e}")
                    replacement = fallback

        # Замена именно этой ссылки (сырая разметка целиком, включая |описание)
        pattern = re.escape(f"[[EVO:{sub_id}") + r'(?:\s*\|\s*[^\]]*)?\]\]'
        resolved = re.sub(pattern, lambda m, r=replacement: r, resolved, count=1)

    return resolved


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
            content, _raw_hyperlinks = await read_cell(
                sym['shard_host'], sym['shard_path'], sym.get('shard_mirror')
            )
        else:
            # Тесты Фазы 0: локальный шард
            content, _raw_hyperlinks = await read_cell_local(
                sym.get('shard_path', f"/evo/test/{symbol_id}.zst")
            )
    except Exception as e:
        content = sym.get('label', 'No content available')
        log.warning(f"Shard read failed for {symbol_id}: {e}")

    # Разворачиваем [[EVO:...]] прямо в контенте — наружу должен уйти
    # самодостаточный, готовый к исполнению текст, без внутренней нотации
    # и без "повисших" ссылок, которые флагман не сможет ни прочитать,
    # ни запросить дальше (у него нет доступа к внутреннему языку ядра).
    content = await _resolve_hyperlinks(content, depth=0, visited={symbol_id})

    # Инкремент рейтинга при вызове
    await increment_rating(symbol_id)

    return {
        "symbol_id": symbol_id,
        "label": sym['label'],
        "content": content,
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
