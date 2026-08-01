"""
Контур Obsidian — БЛОК 06 (часть 2), Фаза 1
Логика и связи: анализ дельты, архивация Тип А/Б, лигатуры, граф, хук-допрос.
Правила: SCL_FRACTAL_PROTOCOL.md разделы 11-17, SCL_SYMBOLIC_NOTATION.md
"""
import logging, asyncio
from core.ai_router import ai_router
from core.archivist import archive, _generate_id
from core.verifier import VerificationResult
from db.pg_client import get_pool, find_symbols, insert_symbol
from db.redis_client import enqueue_write

log = logging.getLogger("evo.obsidian")


async def process(verify_result: VerificationResult, session_id: str,
                  output: str, original_tz: str, applied_stack: list[str],
                  cartridge: dict, deviations: str = ""):
    """
    Точка входа контура Obsidian.
    Вызывается после успешной верификации YMS-MMM.
    Работает асинхронно — пользователь уже получил ответ.
    """
    asyncio.create_task(_run(
        verify_result, session_id, output, original_tz,
        applied_stack, cartridge, deviations
    ))


async def _run(verify_result: VerificationResult, session_id: str,
               output: str, original_tz: str, applied_stack: list[str],
               cartridge: dict, deviations: str):
    try:
        action = verify_result.action

        if action == "record_confirmation":
            await _confirm_existing(session_id, applied_stack)

        elif action == "analyze_delta":
            await _archive_delta(
                session_id, verify_result.delta_type, output, original_tz,
                applied_stack, deviations
            )

        elif action == "record_new_knowledge":
            await archive(
                session_id=session_id, output=output,
                solution_quality="gap_filled", deviations=deviations,
                applied_stack=applied_stack, original_tz=original_tz,
                context={}
            )

        # Фаза 2 утверждения лигатуры-кандидата (core/librarian.py::
        # _record_candidate_ligature, Сценарий Б): если эта сессия
        # пользовалась ещё не подтверждённой сборкой по частям — теперь,
        # когда мы дошли сюда по любой из трёх веток выше, вся цепочка
        # подтверждена работоспособной (result.py вызывает process() только
        # после workability_confirmed=True и полного YMS-MMM) — утверждаем
        # кандидата: становится видимым для всех сессий (is_universal=TRUE).
        from db.redis_client import get_and_clear_candidate_ligature
        from db.pg_client import promote_candidate_ligature
        candidate_id = await get_and_clear_candidate_ligature(session_id)
        if candidate_id:
            await promote_candidate_ligature(candidate_id)

        # Проверка кандидатов на лигатуру
        await _check_ligature_candidates(cartridge)

        # Обновление графа
        await _update_graph_stats(applied_stack)

    except Exception as e:
        log.error(f"[Obsidian] Error: {e}")


async def _confirm_existing(session_id: str, applied_stack: list[str]):
    """
    Тип ideal: R_f +1, обновить applicable_stacks.

    Раньше символы брались из cartridge['instructions'], которое эхом
    возвращал флагман в /result — но symbol_id больше не уходит флагману
    (внутренняя нотация не покидает ядро, см. api/routes/query.py), поэтому
    эхо больше не содержит этих id. Источник истины — серверный план сессии
    в Redis (тот же, что читает /step_done), а не то, что прислал клиент:
    так надёжнее и в принципе правильнее — внутренний учёт не должен
    зависеть от данных, эхом присланных внешней стороной.
    """
    from db.pg_client import increment_rating
    from db.redis_client import get_session_plan
    plan = await get_session_plan(session_id) or []
    pool = await get_pool()
    async with pool.acquire() as conn:
        for step_data in plan:
            sid = step_data.get("symbol_id")
            if sid:
                await increment_rating(sid)
                # Добавить новые стеки
                for s in applied_stack:
                    await conn.execute("""
                        UPDATE scl_symbols
                        SET applicable_stacks =
                            CASE WHEN $2 = ANY(applicable_stacks)
                                 THEN applicable_stacks
                                 ELSE array_append(applicable_stacks, $2) END,
                            last_updated = NOW()
                        WHERE id = $1
                    """, sid, s)
    log.info(f"[Obsidian] Confirmed {len(plan)} symbols, stacks: {applied_stack}")


async def _archive_delta(session_id: str, delta_type: str, output: str, original_tz: str,
                          applied_stack: list[str], deviations: str):
    """
    Тип adapted: определить А или Б и заархивировать.

    Родительский символ — первый шаг из серверного плана сессии (Redis),
    не из эха флагмана (см. _confirm_existing выше — та же причина: эхо
    больше не содержит symbol_id).
    """
    from db.redis_client import get_session_plan
    plan = await get_session_plan(session_id) or []
    if not plan:
        return

    # Берём первый символ из плана как родительский
    parent_id = plan[0].get("symbol_id")

    pool = await get_pool()
    if parent_id:
        async with pool.acquire() as conn:
            parent = await conn.fetchrow(
                "SELECT * FROM scl_symbols WHERE id = $1", parent_id
            )
        if parent:
            parent_dict = dict(parent)
            # N2 fix: vector вычисляется ДО if/else.
            # Ранее ai_router импортировался как r только в блоке "A" →
            # при delta_type=="B" возникал NameError: name "r" is not defined.
            # ai_router уже импортирован в начале файла.
            vector = await ai_router.embed(output[:400])

            if delta_type == "A":
                from core.archivist import _type_a
                await _type_a(parent_dict, output, applied_stack, vector)
                log.info(f"[Obsidian] Тип А: обновлён {parent_id}")
            else:
                from core.archivist import _type_b
                # P8 fix: new_stack = текущий applied_stack
                #         parent_stacks = стек родительского символа
                parent_stacks = parent_dict.get('applicable_stacks', [])
                await _type_b(parent_dict, output, applied_stack,
                               parent_stacks, vector, original_tz)
                log.info(f"[Obsidian] Тип Б: новый символ от {parent_id}")


async def _check_ligature_candidates(cartridge: dict) -> int:
    """
    Проверка тройного подтверждения — SCL_FRACTAL_PROTOCOL.md раздел 6.
    confirmed_by >= 3 → автоматически создать лигатуру.
    Возвращает число реально созданных лигатур (для статистики фоновой
    работы, core/sleep_mode.py::_check_integrity).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Найти все символы с confirmed_by >= 3 без лигатуры
        candidates = await conn.fetch("""
            SELECT id, label, science, section, subsection,
                   confirmed_in, vector, applicable_stacks
            FROM scl_symbols
            WHERE confirmed_by >= 3
              AND id NOT LIKE '%⊕%'
              AND is_legacy = FALSE
            LIMIT 5
        """)

    created = 0
    for cand in candidates:
        # Проверяем: существует ли уже лигатура для этих областей?
        roots = cand['confirmed_in'] or []
        if len(roots) < 2:
            continue

        roots_str = "⊕".join(sorted(roots[:3]))
        ligature_id = f"[{roots_str}]^{{multi}}_{{{cand['subsection'][:4]}_L001}}"

        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT id FROM scl_symbols WHERE id = $1", ligature_id
            )
            if not exists:
                log.info(f"[Obsidian] Создаём лигатуру: {ligature_id}")
                # R_f лигатуры = сумма R_f составных
                rf_sum = await conn.fetchval("""
                    SELECT COALESCE(SUM(rating_frequency), 3)
                    FROM scl_symbols
                    WHERE science = ANY($1::text[])
                """, roots)

                await insert_symbol({
                    "id": ligature_id,
                    "label": f"лигатура: {cand['label'][:60]} | области: {roots_str}",
                    "vector": list(cand['vector']) if cand['vector'] else [],
                    "science": "⊕".join(roots[:3]),  # fix: единый разделитель с ligature_id
                    "section": cand['section'],
                    "subsection": cand['subsection'],
                    "confirmed_by": 3,
                    "confirmed_in": roots,
                    "applicable_stacks": list(cand['applicable_stacks'] or []),
                    "hyperlinks": [cand['id']],
                    "shard_host": "",
                    "shard_path": f"/evo/LIGATURE/{ligature_id}.zst",
                    "rating_frequency": int(rf_sum or 3),
                })
                log.info(f"[Obsidian] Лигатура создана: {ligature_id}")
                created += 1

    return created


async def _update_graph_stats(applied_stack: list[str]):
    """Обновляем статистику для графа знаний."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Топ используемых областей
        top = await conn.fetch("""
            SELECT science, SUM(rating_frequency) as total_rf
            FROM scl_symbols WHERE is_legacy = FALSE
            GROUP BY science ORDER BY total_rf DESC LIMIT 10
        """)
    if top:
        log.debug(f"[Obsidian] Graph top: {[(r['science'], r['total_rf']) for r in top[:3]]}")


async def generate_hook_query(applied_stack: list[str]) -> str:
    """Генерация хук-допроса с учётом стека."""
    stack_str = ", ".join(applied_stack[:3]) if applied_stack else "текущем стеке"
    return f"...или есть что-то ещё новее по этой теме применимое к стеку [{stack_str}]?"
