"""
Архивариус — запись и обновление символов.
Работает асинхронно через очередь — пользователь не ждёт.
"""
import asyncio, logging, re
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
    """Полный цикл архивации — Контур Obsidian."""
    try:
        # 1. Векторизовать новое знание
        vector = await ai_router.embed(output[:500] + " " + original_tz[:200])

        # 2. Similarity check
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
    new_shard = f"/evo/{existing['science'][:3].upper()}/{old_id}_v2.zst"
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
    shard_path = f"/evo/{parent['science'][:3].upper()}/{symbol_id}.zst"
    await write_cell("", shard_path, new_output)
    # Обновляем confirmed_in у родительского символа
    from db.pg_client import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Добавляем science родителя в confirmed_in если новая область
        parent_sci = parent['science'][:2]
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
        "confirmed_in": [parent['science'][:2]],
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
    root = await ai_router.classify(output[:300], "macro_root")
    root = root.strip()[:2]
    symbol_id = await _generate_id(root, "new", "new")
    shard_path = f"/evo/{root.upper()}/{symbol_id}.zst"
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



# P16 fix: маппинг 32 макро-корней → 2-символьные коды для SCL-нотации.
# Без этого science[:2] для русских названий даёт нечитаемые двухбуквенные коды.
# Нотация: τ^{auto}_{zp_0047} — sym должен быть латинским кодом из этого маппинга.
ROOT_CODES: dict[str, str] = {
    # Точные науки
    "Математика": "Mt",   "Физика": "Fx",      "Химия": "Ch",
    "Биология": "Bi",     "Информатика": "Cs",  "Кибернетика": "Cy",
    # Инженерия
    "Технология": "Tc",   "Архитектура": "Ar",  "Механика": "Mc",
    "Электроника": "El",  "Робототехника": "Rb", "Автоматизация": "Au",
    # ИИ и данные
    "ИИ": "Ai",           "МашОбучение": "Ml",  "Данные": "Da",
    "Алгоритмы": "Al",    "БазыДанных": "Db",   "Сети": "Nt",
    # Философия и гуманитарные
    "Философия": "Fl",    "Лингвистика": "Ln",  "Психология": "Ps",
    "Социология": "So",   "Экономика": "Ec",    "Право": "Lw",
    # Практика
    "Медицина": "Md",     "Педагогика": "Pd",   "Менеджмент": "Mg",
    "Маркетинг": "Mk",    "Дизайн": "Ds",       "Искусство": "Is",
    # Системные
    "Безопасность": "Sc", "Инфраструктура": "If",
}

def _get_root_code(science: str) -> str:
    """Возвращает 2-символьный код макро-корня для SCL-нотации."""
    if science in ROOT_CODES:
        return ROOT_CODES[science]
    # Fallback: первые 2 заглавных ASCII символа из строки
    ascii_chars = [c for c in science if c.isascii() and c.isalpha()]
    if len(ascii_chars) >= 2:
        return (ascii_chars[0] + ascii_chars[1]).upper()
    # Последний резерв: hex от первых 2 байт
    return science[:2].encode('utf-8').hex()[:2].upper()

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
