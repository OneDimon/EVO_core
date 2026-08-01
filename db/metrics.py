"""
Metrics — метаданные обращений для админ-панели владельца и личного
кабинета пользователя (evo_request_log, миграция 009).

Правило Архитектора: НЕ собираем содержимое пользовательских проектов или
решений — ни текст запроса, ни ответ ядра. Только: кто обратился, куда,
за сколько (латентность), с каким статусом, сколько токенов потрачено
ядром реально и сколько потратил бы флагман, если бы генерировал это сам.

Механизм — contextvars, не аргументы функций: core/ai_router.py и
core/librarian.py находятся глубоко в цепочке вызовов одного запроса и не
должны знать о существовании лога метрик. Один и тот же asyncio-таск
(запрос обрабатывается без create_task от начала до конца в
api/middleware/security.py) — значит contextvar, выставленный внутри
ai_router.embed(), виден в middleware после return без явной передачи.

Ограничение: фоновые задачи, запущенные через asyncio.create_task
(core/archivist.py, core/immune_system.py — работают ПОСЛЕ ответа
пользователю), получают копию контекста при создании таска — их
собственные добавления токенов НЕ долетают до уже отправленного лога
этого запроса. Это осознанное упрощение, не баг: их стоимость мала
(эмбеддинг для similarity-check) и не блокирует ответ пользователю.
"""
import contextvars
import logging

log = logging.getLogger("evo.metrics")

_tokens_actual: contextvars.ContextVar[int] = contextvars.ContextVar(
    "evo_tokens_actual", default=0)
_tokens_baseline: contextvars.ContextVar[int] = contextvars.ContextVar(
    "evo_tokens_baseline", default=0)
_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "evo_metrics_session_id", default="")
_scenario: contextvars.ContextVar[str] = contextvars.ContextVar(
    "evo_metrics_scenario", default="")
_symbol_confirmed_by: contextvars.ContextVar[int] = contextvars.ContextVar(
    "evo_metrics_confirmed_by", default=0)
_symbol_rating: contextvars.ContextVar[int] = contextvars.ContextVar(
    "evo_metrics_rating", default=0)

# Множитель "во сколько раз многословнее был бы сырой сгенерированный
# ответ ИИ по сравнению с уже дистиллированной инструкцией из библиотеки" —
# консервативная оценка, не маркетинговое число: LLM обычно добавляет
# объяснения/оговорки/форматирование, которых нет в готовом решении.
BASELINE_VERBOSITY_MULTIPLIER = 1.4
CHARS_PER_TOKEN_ESTIMATE = 4  # грубая, общепринятая эвристика для смешанного RU/EN текста


def reset():
    """Вызывается в начале обработки запроса (middleware)."""
    _tokens_actual.set(0)
    _tokens_baseline.set(0)
    _session_id.set("")
    _scenario.set("")
    _symbol_confirmed_by.set(0)
    _symbol_rating.set(0)


def add_tokens_actual(text_in: str = "", text_out: str = ""):
    """core/ai_router.py вызывает это при каждом реальном обращении к AI-провайдеру."""
    n = (len(text_in) + len(text_out)) // CHARS_PER_TOKEN_ESTIMATE
    _tokens_actual.set(_tokens_actual.get() + max(0, n))


def add_tokens_baseline(delivered_content: str):
    """
    core/librarian.py вызывает это при выдаче готового содержимого шага —
    оценка, сколько токенов вывода потратил бы флагман, если бы вместо
    готового решения из библиотеки генерировал его сам с нуля.
    """
    n = int(len(delivered_content) / CHARS_PER_TOKEN_ESTIMATE * BASELINE_VERBOSITY_MULTIPLIER)
    _tokens_baseline.set(_tokens_baseline.get() + max(0, n))


def set_session_id(session_id: str):
    _session_id.set(session_id or "")


def set_delivery_meta(scenario: str = "", confirmed_by: int = 0, rating: int = 0):
    """
    Честные, проверяемые киллер-метрики для ЛК: scenario ('full'|'partial'
    |'gap') и метаданные топового выданного символа — сколько раз он
    независимо подтверждён (confirmed_by) и как часто используется
    (rating). Вызывается из api/routes/query.py после librarian.search().
    """
    if scenario:
        _scenario.set(scenario)
    if confirmed_by:
        _symbol_confirmed_by.set(confirmed_by)
    if rating:
        _symbol_rating.set(rating)


def snapshot() -> dict:
    return {
        "tokens_actual": _tokens_actual.get(),
        "tokens_baseline_est": _tokens_baseline.get(),
        "session_id": _session_id.get(),
        "scenario": _scenario.get(),
        "symbol_confirmed_by": _symbol_confirmed_by.get(),
        "symbol_rating": _symbol_rating.get(),
    }


async def log_request(user_id: str, api_key_id: str, endpoint: str,
                       status: str, error_type: str, latency_ms: int):
    """
    Пишет одну строку в evo_request_log. Вызывается из middleware после
    завершения запроса — не блокирует ответ пользователю (fire-and-forget
    через asyncio.create_task на стороне вызывающего).
    """
    snap = snapshot()
    try:
        from db.pg_client import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO evo_request_log
                (user_id, api_key_id, session_id, endpoint, status, error_type,
                 latency_ms, tokens_actual, tokens_baseline_est,
                 scenario, symbol_confirmed_by, symbol_rating)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            """, user_id, api_key_id, snap["session_id"] or None, endpoint,
                status, error_type, latency_ms,
                snap["tokens_actual"], snap["tokens_baseline_est"],
                snap["scenario"] or None,
                snap["symbol_confirmed_by"] or None,
                snap["symbol_rating"] or None)
    except Exception as e:
        # Лог метрик не должен ронять запрос пользователя ни при каких
        # обстоятельствах — сбой здесь только логируется.
        log.warning(f"[Metrics] Не удалось записать evo_request_log: {e}")
