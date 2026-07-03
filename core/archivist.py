"""
Архивариус — запись и обновление символов.
Работает асинхронно через очередь — пользователь не ждёт.
"""
import asyncio, logging, re, hashlib
from datetime import datetime
from db.pg_client import find_symbols, insert_symbol, update_symbol_type_a, increment_rating
from db.redis_client import enqueue_write
from shards.shard_client import write_cell
from core.ai_router import ai_router

log = logging.getLogger("evo.archivist")

async def archive(session_id: str, output: str, solution_quality: str,
                  deviations: str, applied_stack: list[str],
                  original_tz: str, context: dict):
    """Точка входа архивации — ставит в очередь, не блокирует."""
    await enqueue_write({
        "session_id": session_id,
        "output": output,
        "solution_quality": solution_quality,
        "deviations": deviations,
        "applied_stack": applied_stack,
        "original_tz": original_tz,
        "context": context,
        "timestamp": datetime.now().isoformat()
    })
    # Запускаем фоновую задачу
    asyncio.create_task(_process_archive(
        output, solution_quality, deviations, applied_stack, original_tz, context
    ))


async def _process_archive(output: str, solution_quality: str,
                            deviations: str, applied_stack: list[str],
                            original_tz: str, context: dict):
    """
    Полный цикл архивации — Контур Obsidian.

    Защита от гонки при конкурентной записи: при тысячах пользователей два
    флагмана могут одновременно решать очень похожие задачи. Оба пройдут
    similarity check ДО того, как второй увидит запись первого (классическая
    check-then-act гонка) — оба создадут почти-дубль вместо того чтобы один
    стал Тип А/Б другого. PostgreSQL advisory lock, ключ — грубый бакет по
    первым 16 измерениям вектора (округление до 1 знака), сериализует ТОЛЬКО
    семантически близкие записи — не блокирует несвязанные записи других
    пользователей (не глобальный лок, не убивает пропускную способность).
    Работает между всеми воркерами/процессами (лок на уровне БД, не Python).
    """
    from db.pg_client import get_pool
    try:
        # 1. Векторизовать новое знание
        vector = await ai_router.embed(output[:500] + " " + original_tz[:200])

        # 2. Advisory lock на грубый бакет вектора — сериализует конкурентные
        # записи одной семантической области, не трогая остальные
        bucket_raw = ",".join(f"{v:.1f}" for v in vector[:16])
        lock_id = int(hashlib.md5(bucket_raw.encode()).hexdigest()[:15], 16) % (2**62)

        pool = await get_pool()
        async with pool.acquire() as lock_conn:
            await lock_conn.execute("SELECT pg_advisory_lock($1)", lock_id)
            try:
                # 3. Similarity check — теперь под локом, второй конкурентный
                # вызов с похожим вектором дождётся завершения первого и
                # увидит уже вставленный символ как кандидата на Тип А/Б
                similar = await find_symbols(vector, top_k=3, exclude_legacy=False)
                top_sim = similar[0].get('similarity', 0) if similar else 0

                if top_sim > 0.95:
                    await _type_a(similar[0], output, applied_stack, vector)
                elif top_sim > 0.75:
                    # P3 fix: new_stack = текущий applied_stack (новое применение)
                    #         applied_stack = стек родительского символа
                    parent_stacks = similar[0].get('applicable_stacks', [])
                    await _type_b(similar[0], output, applied_stack, parent_stacks, vector, original_tz)
                else:
                    await _new_symbol(output, applied_stack, vector, original_tz)
            finally:
                await lock_conn.execute("SELECT pg_advisory_unlock($1)", lock_id)

    except Exception as e:
        log.error(f"Archive failed: {e}")


async def _type_a(existing: dict, new_output: str,
                   applied_stack: list[str], vector: list[float]):
    """Тип А: перезапись — улучшение существующего решения.
    Старое решение помечается is_legacy=True + superseded_by указывает на новое.
    """
    from db.pg_client import get_pool
    evolution_note = await ai_router.generate(
        f"old: {existing['label']} | new: {new_output[:200]}", "evolution_note"
    )
    old_id = existing['id']
    # fix: папка шарда именуется коротким символом (τ), не 3-буквенным
    # срезом полного имени — консистентно с ID и остальными путями
    _root_symbol = _get_root_code(existing['science'])
    new_shard = f"/evo/{_root_symbol}/{old_id}_v2.zst"
    await write_cell("", new_shard, new_output)

    # N9 fix: проверяем результат — update_symbol_type_a теперь возвращает bool
    applied = await update_symbol_type_a(old_id, new_shard, evolution_note, old_id + "_pre")
    if not applied:
        log.warning(f"[Тип А] {old_id}: UPDATE не применился (concurrent update) — "
                     f"shard {new_shard} записан, но символ не обновлён в БД")

    # Добавляем applied_stack в applicable_stacks
    if applied_stack:
        pool = await get_pool()
        async with pool.acquire() as conn:
            for s in applied_stack:
                await conn.execute("""
                    UPDATE scl_symbols
                    SET applicable_stacks = array_append(
                        CASE WHEN $2 = ANY(applicable_stacks) THEN applicable_stacks
                        ELSE applicable_stacks END, $2)
                    WHERE id = $1 AND NOT ($2 = ANY(applicable_stacks))
                """, old_id, s)

    log.info(f"[Тип А] Updated {old_id} → {new_shard}")


async def _type_b(parent: dict, new_output: str, new_stack: list[str],
                   applied_stack: list[str], vector: list[float], original_tz: str):
    """Тип Б: новый символ для других обстоятельств."""
    symbol_id = await _generate_id(parent['science'], parent['section'],
                                     parent['subsection'])
    _root_symbol = _get_root_code(parent['science'])
    shard_path = f"/evo/{_root_symbol}/{symbol_id}.zst"
    await write_cell("", shard_path, new_output)
    # Обновляем confirmed_in у родительского символа
    from db.pg_client import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        # fix: confirmed_in хранит КОРОТКИЙ символ (τ), как в примере
        # LOCAL_MODEL_INSTRUCTIONS.md ("confirmed_in: [\"τ\", \"κ\", \"η\"]"),
        # не обрезок полного имени (было science[:2] → мусор вроде "Те")
        parent_sci = _get_root_code(parent['science'])
        await conn.execute("""
            UPDATE scl_symbols
            SET confirmed_in = array_append(confirmed_in, $2),
                confirmed_by = confirmed_by + 1,
                last_updated = NOW()
            WHERE id = $1 AND NOT ($2 = ANY(confirmed_in))
        """, parent['id'], parent_sci)
        # Проверяем: confirmed_by >= 3 → кандидат на лигатуру
        row = await conn.fetchrow("SELECT confirmed_by, confirmed_in FROM scl_symbols WHERE id=$1", parent['id'])
        if row and row['confirmed_by'] >= 3:
            log.info(f"[Лигатура] Кандидат: {parent['id']} confirmed_in={row['confirmed_in']}")

    await insert_symbol({
        "id": symbol_id,
        "label": f"задача: {original_tz[:80]} | стек: {','.join(new_stack[:3])}",
        "vector": vector,
        "science": parent['science'],
        "section": parent['section'],
        "subsection": parent['subsection'],
        "evolved_from": parent['id'],
        "evolution_note": f"новые условия: стек {new_stack}",
        "applicable_stacks": applied_stack,
        "confirmed_in": [_get_root_code(parent['science'])],  # короткий символ, не обрезок имени
        "shard_host": "", "shard_path": shard_path,
    })
    log.info(f"[Тип Б] Created {symbol_id}")


async def _new_symbol(output: str, applied_stack: list[str],
                       vector: list[float], original_tz: str,
                       source_url: str = None, source_rating: int = 0,
                       source_type: str = None, auto_collected: bool = False):
    """Новый символ с нуля (gap_filled / Канал 1 auto_collected).
    
    Параметры Канала 1 (knowledge_collector):
        source_url      — URL откуда взято знание
        source_rating   — stars/downloads источника
        source_type     — github|npm|pypi|n8n|official|cli_plugin
        auto_collected  — True если собрано в режиме СОН (Канал 1)
    """
    # fix: classify() теперь возвращает ПОЛНОЕ каноническое имя ("Технология/Инженерия"),
    # не голый символ. root хранится как есть в поле science (совместимо с
    # WHERE science=$1 в knowledge_collector). Короткий символ для ID и пути
    # выводится через _get_root_code внутри _generate_id и явно здесь для пути.
    root = await ai_router.classify(output[:300], "macro_root")
    symbol_id = await _generate_id(root, "new", "new")
    _root_symbol = _get_root_code(root)
    shard_path = f"/evo/{_root_symbol}/{symbol_id}.zst"
    await write_cell("", shard_path, output)
    await insert_symbol({
        "id": symbol_id,
        "label": f"задача: {original_tz[:80]} | решение: {output[:80]}",
        "vector": vector,
        "science": root,
        "section": "new",
        "subsection": "new",
        "applicable_stacks": applied_stack,
        "shard_host": "", "shard_path": shard_path,
        # Канал 1
        "source_url": source_url,
        "source_rating": source_rating,
        "source_type": source_type,
        "auto_collected": auto_collected,
    })
    log.info(f"[{'Канал1' if auto_collected else 'Новый'}] Created {symbol_id}"
             + (f" src={source_url}" if source_url else ""))



# ИСПРАВЛЕНО (после ещё одной сверки с оригиналом): предыдущие две попытки
# (P16 — латиница Tc/Mt, затем N12-фикс — своя выдуманная греческая таблица)
# НЕ совпадали с официальной таблицей из SCL_FRACTAL_PROTOCOL.md раздел 5 —
# защищённого фундаментального документа с исходными 32 корнями Архитектора.
# Эта версия — точная копия таблицы раздела 5, без отсебятины. Не изменять
# без явного разрешения Архитектора (см. правило 1 раздела 17 протокола).
#
# Обрати внимание: символ #3 — латинская "M" (не греческая μ, которая занята
# под "Маркетинг/Коммуникации" #25). Это осознанный выбор в исходной таблице,
# сохранён как есть.
ROOT_CODES: dict[str, str] = {
    "Философия/Логика":                       "Φ",
    "Лингвистика/Семантика":                   "Λ",
    "Математика/Алгебра":                      "M",
    "Физика/Энергия":                          "γ",
    "Химия/Материаловедение":                  "ζ",
    "Биология/Генетика":                       "β",
    "Нейробиология/Психология":                "η",
    "Кибернетика/Алгоритмика":                 "κ",
    "Экономика/Ресурсы":                       "ε",
    "Технология/Инженерия":                    "τ",
    "Социология/Право":                        "σ",
    "Астрономия/Космология":                   "α",
    "История/Архивоведение":                   "χ",
    "Искусство/Эстетика":                      "ψ",
    "Медицина/Здоровье":                       "δ",
    "Экология/Климат":                         "ξ",
    "Игровые системы/Геймдизайн":              "Ω",
    "Политология/Управление":                  "Π",
    "Теология/Мифология":                      "Θ",
    "Педагогика/Когнитология":                 "Ξ",
    "Антропология/Культурология":              "Ψ",
    "Системный дизайн/Архитектура":            "Σ",
    "Финансы/Инвестиции":                      "Δ",
    "Геология/География":                      "Γ",
    "Маркетинг/Коммуникации":                  "μ",
    "Нейронные сети/ИИ":                       "ν",
    "Робототехника/Мехатроника":               "ρ",
    "Информационная безопасность":             "ι",
    "Термодинамика/Статфизика":                "θ",
    "Прикладная математика/Статистика":        "π",
    "Квантовая физика/Квантовые вычисления":   "ω",
    "Функциональное программирование/Теория типов": "λ",
}

def _get_root_code(science: str) -> str:
    """
    Возвращает базовый символ макро-корня по официальной таблице
    SCL_FRACTAL_PROTOCOL.md раздел 5 (32 корня, неизменяемы).
    """
    if science in ROOT_CODES:
        return ROOT_CODES[science]
    # Неизвестный корень не должен встречаться при валидных данных — новые
    # корни НЕ создаются (правило 1, раздел 17). Это сигнал ошибки классификации
    # выше по стеку (ai_router.classify(task="macro_root") вернул то, чего нет
    # в таблице), а не повод придумать 33-й корень.
    log.error(
        f"[Archivist] КРИТИЧНО: классификатор вернул несуществующий макро-корень "
        f"'{science}' — 32 корня неизменяемы (SCL_FRACTAL_PROTOCOL.md §17.1). "
        f"Используется Φ (Философия/Логика) как безопасный дефолт до ручного разбора."
    )
    return "Φ"

async def _generate_id(science: str, section: str, subsection: str) -> str:
    """Генерация ID по нотации SCL: τ^{auto}_{zp_0047}"""
    from db.pg_client import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM scl_symbols WHERE science=$1 AND section=$2 AND subsection=$3",
            science, section, subsection
        )
    num = str(int(count or 0) + 1).zfill(4)
    sec = re.sub(r'[^a-zA-Z0-9]', '_', section[:8].lower())
    sub = re.sub(r'[^a-zA-Z0-9]', '_', subsection[:4].lower())
    sym = _get_root_code(science)  # P16 fix: маппинг 32 корней вместо science[:2]
    return f"{sym}^{{{sec}}}_{{{sub}_{num}}}"
