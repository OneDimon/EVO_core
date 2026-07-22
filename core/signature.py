"""
Signature — HMAC-подпись протокола ядро↔флагман (evo_signature).

Правило источника (FLAGSHIP_SYSTEM_PROMPT.md / .claude/CLAUDE.md БЛОК 5,
п.11): "Верификация evo_signature на каждом ответе ядра." Симметрично —
каждый запрос флагмана внутри сессии подписан тем же session_key, выданным
при /handshake (см. api/routes/handshake.py::handshake, hmac_key в ответе).

Единственная точка вычисления/проверки подписи во всей системе — не
дублировать HMAC-логику в отдельных роутах (тот же принцип централизации,
что и core/ai_router.py для AI-вызовов).

Явное решение по охвату: примеры JSON в протоколе показывают evo_signature
только у /query и /result, но правило п.11 требует подписи "каждого ответа
ядра" без исключений. Применяем подпись/проверку единообразно ко всем
протокольным эндпоинтам сессии — /concierge, /query, /result, /step_done,
/hook_reply — а не только к тем двум, что попали в иллюстративные примеры.
Частичное покрытие было бы даже более запутывающим, чем полное его отсутствие.

Канонизация payload: json.dumps(sort_keys=True) над телом БЕЗ поля
evo_signature — детерминированная сериализация, не зависящая от порядка
ключей на стороне отправителя/получателя.
"""
import hmac
import hashlib
import json
import logging
import os

from db.sessions import get_session

log = logging.getLogger("evo.signature")

DEV_MODE = os.getenv("EVO_ENV", "production") == "development"


def _canonical(payload: dict) -> bytes:
    clean = {k: v for k, v in payload.items() if k != "evo_signature"}
    return json.dumps(
        clean, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), default=str
    ).encode()


def _compute(payload: dict, session_key: str) -> str:
    return hmac.new(
        session_key.encode(), _canonical(payload), hashlib.sha256
    ).hexdigest()


async def sign_response(payload: dict, session_id: str) -> dict:
    """
    Добавляет evo_signature к ответу ядра перед отправкой флагману.

    Если сессия не найдена (гонка сразу после /handshake, БД временно
    недоступна и т.п.) — ответ уходит БЕЗ подписи, но это логируется как
    log.error, не молча (Урок 3 из .claude/CLAUDE.md: тихий fallback скрывает
    сломанную защиту месяцами). Флагман, следующий протоколу и
    верифицирующий evo_signature на своей стороне, увидит отсутствие поля
    и должен считать такой ответ непроверенным.
    """
    session = await get_session(session_id)
    if not session:
        log.error(
            f"[Signature] Сессия {session_id} не найдена при подписи ответа "
            f"— ответ отправлен БЕЗ evo_signature"
        )
        return payload
    payload["evo_signature"] = _compute(payload, session["hmac_key"])
    return payload


async def verify_request(payload: dict, session_id: str) -> bool:
    """
    Проверяет evo_signature входящего запроса флагмана.

    В development (EVO_ENV=development) проверка пропускается — согласовано
    с остальным security.py (EVOSecurityMiddleware тоже полностью отключает
    auth в dev_mode), но пропуск логируется явно (log.debug), а не тихо.
    В production отсутствие/несовпадение подписи — отказ (вызывающий роут
    должен вернуть 401).
    """
    if DEV_MODE:
        log.debug(
            f"[Signature] DEV MODE: пропуск проверки evo_signature, "
            f"session={session_id}"
        )
        return True

    session = await get_session(session_id)
    if not session or not session.get("is_active"):
        log.warning(f"[Signature] Сессия {session_id} не найдена/неактивна")
        return False

    signature = payload.get("evo_signature") or ""
    if not signature:
        log.warning(f"[Signature] Запрос без evo_signature, session={session_id}")
        return False

    expected = _compute(payload, session["hmac_key"])
    valid = hmac.compare_digest(expected, signature)
    if not valid:
        log.warning(f"[Signature] Неверная подпись evo_signature, session={session_id}")
    return valid
