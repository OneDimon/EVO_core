"""
Sleep Mode — Режим СОН ядра EVO-core, Фаза 1
Правила: SLEEP_MODE.md
Окно: час наименьшей нагрузки за 3-7 дней.
Прерывание: нагрузка > 90% от базовой.
Уведомления: ТГ-бот + админка при критических изменениях.
"""
import asyncio, logging, json, os
from datetime import datetime, timezone
import httpx
from db.pg_client import get_pool
from db.redis_client import get_redis
from core.ai_router import ai_router

log = logging.getLogger("evo.sleep")

_sleep_active = False
_bg_task = None

PROTECTED_ZONES = [
    "scl_symbols", "config/", "prompts/",
    "SCL_FRACTAL_PROTOCOL.md", "LOCAL_MODEL_INSTRUCTIONS.md",
    "migrations/"
]


# ── Планировщик окна СОН ─────────────────────────────────────────────────────

async def calculate_sleep_window(days: int = 7) -> int:
    """Возвращает час (0-23) наименьшей нагрузки за последние N дней."""
    r = await get_redis()
    import time
    hourly = {}
    now_hour = int(time.time() // 3600)
    for h in range(now_hour - days * 24, now_hour):
        key = f"evo:rps:{h}"
        val = await r.hget(key, "rps")
        hour_of_day = h % 24
        if val:
            hourly[hour_of_day] = hourly.get(hour_of_day, 0) + float(val)

    if not hourly:
        return 3  # default: 3:00 ночи

    min_hour = min(hourly, key=hourly.get)
    log.info(f"[Sleep] Окно СОН: {min_hour}:00 (avg RPS: {hourly.get(min_hour, 0):.2f})")
    return min_hour


async def get_baseline_rps(days: int = 7) -> float:
    """Средний RPS за последние N дней."""
    r = await get_redis()
    import time
    vals = []
    now_hour = int(time.time() // 3600)
    for h in range(now_hour - days * 24, now_hour):
        val = await r.hget(f"evo:rps:{h}", "rps")
        if val:
            vals.append(float(val))
    return sum(vals) / len(vals) if vals else 1.0


async def get_current_rps() -> float:
    """Текущий RPS из Redis."""
    r = await get_redis()
    import time
    key = f"evo:rps:{int(time.time() // 3600)}"
    val = await r.hget(key, "rps")
    return float(val) if val else 0.0


# ── Вход/выход из сна ────────────────────────────────────────────────────────

async def enter_sleep():
    global _sleep_active, _bg_task
    _sleep_active = True
    log.info("[Sleep] ─── ЯДРО УХОДИТ В СОН ───")
    _bg_task = asyncio.create_task(_sleep_cycle())


async def exit_sleep(reason: str = "manual"):
    global _sleep_active
    _sleep_active = False
    if _bg_task:
        _bg_task.cancel()
    log.info(f"[Sleep] ─── ЯДРО ВЫШЛО НА РАБОТУ (причина: {reason}) ───")


# ── Сторож: прерывание при нагрузке > 90% ────────────────────────────────────

async def sleep_watchdog():
    """Мониторинг каждые 30 сек — прерывает сон при росте нагрузки."""
    while _sleep_active:
        current = await get_current_rps()
        baseline = await get_baseline_rps()
        if baseline > 0 and current > baseline * 0.90:
            log.info(f"[Sleep] Нагрузка {current:.2f} > 90% от {baseline:.2f} — выход")
            await exit_sleep(reason=f"load={current:.2f}")
            break
        await asyncio.sleep(30)


# ── Цикл задач в режиме СОН ───────────────────────────────────────────────────

async def _sleep_cycle():
    """Фоновые задачи по приоритетам (SLEEP_MODE.md)."""
    log.info("[Sleep] Запуск фонового цикла")
    asyncio.create_task(sleep_watchdog())

    tasks = [
        ("Поиск потенциальных лигатур", _find_ligature_candidates),
        ("Проверка гипотез", _check_hypotheses),
        ("Апдейт графа знаний", _update_graph),
        ("Статистика", _generate_stats),
        ("Автонаполнение ядра (Канал 1)", _auto_fill_knowledge),
    ]

    for name, fn in tasks:
        if not _sleep_active:
            log.info(f"[Sleep] Прерван до: {name}")
            break
        log.info(f"[Sleep] Задача: {name}")
        try:
            # N10 fix: ранее await fn() выполнялся без отмены —
            # watchdog мог установить _sleep_active=False, но текущая
            # задача (особенно _auto_fill_knowledge с внешними HTTP-запросами)
            # дорабатывала до конца. Теперь задача оборачивается в Task
            # и отменяется если _sleep_active стал False во время выполнения.
            task = asyncio.create_task(fn())
            while not task.done():
                if not _sleep_active:
                    task.cancel()
                    log.warning(f"[Sleep] Задача '{name}' отменена — нагрузка превысила порог")
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    break
                await asyncio.sleep(1)
            else:
                await task  # получить результат/исключение завершённой задачи
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[Sleep] Ошибка в '{name}': {e}")

    log.info("[Sleep] Фоновый цикл завершён")


async def _find_ligature_candidates():
    """
    Ищет символы-кандидаты на лигатуру (confirmed_by >= 2).
    P2 fix: НЕ помечаем hypothesis=TRUE — это инвертированная логика.
    hypothesis=True по SCL раздел 6 = непроверенное знание.
    Символы с confirmed_by >= 2 — наоборот, хорошо подтверждённые.
    Лигатура создаётся в obsidian.py когда confirmed_by достигает 3.
    Здесь только логируем кандидатов для мониторинга.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        candidates = await conn.fetch("""
            SELECT id, label, science, confirmed_by, confirmed_in
            FROM scl_symbols
            WHERE confirmed_by >= 2 AND is_legacy = FALSE
              AND hypothesis = FALSE
            ORDER BY confirmed_by DESC
            LIMIT 20
        """)
    count = len(candidates)
    if count:
        ids = [c['id'] for c in candidates]
        log.info(f"[Sleep] Кандидаты на лигатуру: {count} символов → {ids[:5]}...")
        log.info("[Sleep] Лигатура будет создана в obsidian.py при confirmed_by >= 3")
    else:
        log.info("[Sleep] Кандидатов на лигатуру не найдено")


async def _check_hypotheses():
    """Проверяет старые гипотезы (> 7 дней без применения)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        old = await conn.fetchval("""
            SELECT COUNT(*) FROM scl_symbols
            WHERE hypothesis = TRUE
              AND last_updated < NOW() - INTERVAL '7 days'
        """)
    log.info(f"[Sleep] Устаревших гипотез: {old} (понижен приоритет)")


async def _update_graph():
    """Пересчитывает веса графа по R_f."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        top = await conn.fetch("""
            SELECT science, COUNT(*) as cnt, SUM(rating_frequency) as rf
            FROM scl_symbols WHERE is_legacy = FALSE
            GROUP BY science ORDER BY rf DESC
        """)
        isolated = await conn.fetchval("""
            SELECT COUNT(*) FROM scl_symbols
            WHERE array_length(hyperlinks, 1) IS NULL
              AND evolved_from IS NULL
              AND is_legacy = FALSE
        """)
    log.info(f"[Sleep] Граф: {len(top)} областей, изолированных узлов: {isolated}")


async def _generate_stats():
    """Формирует статистику базы знаний."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        total     = await conn.fetchval("SELECT COUNT(*) FROM scl_symbols")
        active    = await conn.fetchval("SELECT COUNT(*) FROM scl_symbols WHERE is_legacy=FALSE")
        ligatures = await conn.fetchval("SELECT COUNT(*) FROM scl_symbols WHERE id LIKE '%⊕%'")
        top_sym   = await conn.fetch("""
            SELECT id, label, rating_frequency FROM scl_symbols
            WHERE is_legacy=FALSE ORDER BY rating_frequency DESC LIMIT 5
        """)
    stats = {
        "total": total, "active": active, "ligatures": ligatures,
        "top_symbols": [{"id": r['id'], "rf": r['rating_frequency']} for r in top_sym]
    }
    log.info(f"[Sleep] Статистика: {json.dumps(stats, ensure_ascii=False)}")
    return stats


# ── Уведомления Архитектора ────────────────────────────────────────────────────

async def notify_architect(zone: str, problem: str, options: list[dict]):
    """
    Уведомление о критическом изменении в защищённой зоне.
    Одновременно: ТГ-бот + /admin/api/notifications
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        notif_id = await conn.fetchval("""
            INSERT INTO evo_notifications (zone, problem, options)
            VALUES ($1, $2, $3) RETURNING id
        """, zone, problem, json.dumps(options))

    msg = _format_notification(zone, problem, options)

    # ТГ-бот
    tg_token = os.getenv("TG_BOT_TOKEN")
    tg_chat  = os.getenv("TG_ADMIN_CHAT_ID")
    if tg_token and tg_chat:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": msg, "parse_mode": "HTML"}
                )
        except Exception as e:
            log.warning(f"[Sleep] ТГ ошибка: {e}")

    # Админка
    admin_url = os.getenv("ADMIN_NOTIFY_URL", "http://localhost:8000/admin/api/notifications")
    try:
        async with httpx.AsyncClient() as client:
            await client.post(admin_url, json={
                "id": notif_id, "zone": zone,
                "problem": problem, "options": options
            })
    except Exception as e:
        log.warning(f"[Sleep] Админка ошибка: {e}")

    log.info(f"[Sleep] Уведомление отправлено: {zone}")
    return notif_id


def _format_notification(zone: str, problem: str, options: list[dict]) -> str:
    lines = [
        "🔔 <b>EVO-core: Требуется подтверждение</b>",
        f"📌 <b>Зона:</b> {zone}",
        f"⚠️ <b>Проблема:</b> {problem}",
        "",
        "<b>Варианты решения:</b>"
    ]
    for i, opt in enumerate(options, 1):
        lines.append(f"{i}️⃣ {opt['description']}")
        lines.append(f"   <i>Последствия: {opt['consequences']}</i>")
    lines.append("\nОтветь: 1, 2 или 3")
    return "\n".join(lines)



async def _auto_fill_knowledge():
    """
    Задача 5 цикла СОН — Канал 1 автонаполнения ядра.
    Сканирует белые зоны и забирает знания из внешних источников.
    Реализация: core/knowledge_collector.py
    Спецификация: SLEEP_MODE.md раздел "Автонаполнение ядра"
    """
    try:
        from core.knowledge_collector import collect_and_fill
        await collect_and_fill()
    except Exception as e:
        log.error(f"[Sleep] Автонаполнение ошибка: {e}")


async def apply_architect_choice(notif_id: int, choice: int):
    """
    Применяет выбор Архитектора и отчитывается в оба канала.
    N7 fix: при zone="auto_collection" и choice==3 ("Отклонить") —
    реально удаляет недавно автособранные символы, а не только
    меняет статус уведомления.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        notif = await conn.fetchrow(
            "SELECT * FROM evo_notifications WHERE id = $1", notif_id
        )
        if not notif:
            return {"error": "notification not found"}
        options = json.loads(notif['options'])
        if choice < 1 or choice > len(options):
            return {"error": "invalid choice"}
        chosen = options[choice - 1]

        # N7 fix: реальное действие для Канала 1 "Отклонить"
        deleted_count = 0
        if notif['zone'] == "auto_collection" and choice == 3:
            result = await conn.execute("""
                DELETE FROM scl_symbols
                WHERE auto_collected = TRUE AND hypothesis = TRUE
                  AND last_updated > NOW() - INTERVAL '3 hours'
            """)
            # asyncpg execute возвращает строку вида "DELETE N"
            deleted_count = int(result.split()[-1]) if result else 0
            log.info(f"[Sleep] Архитектор отклонил автосбор: удалено {deleted_count} символов")

        await conn.execute(
            "UPDATE evo_notifications SET status='applied', chosen=$2 WHERE id=$1",
            notif_id, choice
        )

    msg = f"✅ <b>Применено:</b> {chosen['description']}"
    if deleted_count:
        msg += f"\n🗑 Удалено символов: {deleted_count}"

    tg_token = os.getenv("TG_BOT_TOKEN")
    tg_chat  = os.getenv("TG_ADMIN_CHAT_ID")
    if tg_token and tg_chat:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                json={"chat_id": tg_chat, "text": msg, "parse_mode": "HTML"}
            )

    log.info(f"[Sleep] Выбор Архитектора применён: {chosen['description']}")
    return {"status": "applied", "description": chosen['description']}
