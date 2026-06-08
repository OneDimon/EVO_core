"""
Telegram Webhook — приём ответов Архитектора на уведомления.
POST /api/v1/tg/webhook — Telegram отправляет сообщения сюда.
Архитектор отвечает: 1, 2 или 3 → применяем выбранное решение.
Правила: SLEEP_MODE.md — notify_architect + apply_architect_choice
"""
import logging, os
from fastapi import APIRouter, Request, HTTPException

log = logging.getLogger("evo.tg_webhook")
router = APIRouter()


@router.post("/tg/webhook")
async def tg_webhook(request: Request):
    """
    Telegram Bot Webhook.
    Настраивается командой: setWebhook → /api/v1/tg/webhook
    """
    # Верифицируем секрет Telegram
    tg_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    expected = os.getenv("TG_WEBHOOK_SECRET", "")
    if expected and tg_secret != expected:
        raise HTTPException(403, "Invalid Telegram webhook secret")

    body = await request.json()
    message = body.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip()

    # Проверяем что это Архитектор
    admin_chat_id = os.getenv("TG_ADMIN_CHAT_ID", "")
    if admin_chat_id and chat_id != admin_chat_id:
        log.warning(f"[TG] Сообщение от неизвестного chat_id: {chat_id}")
        return {"ok": True}  # игнорируем, но не раскрываем ошибку

    log.info(f"[TG] Получено от Архитектора: '{text}'")

    # Парсим ответ: ожидаем "1", "2" или "3"
    # Также поддерживаем формат "notif:123:2" для явного указания ID уведомления
    choice = None
    notif_id = None

    if text.startswith("notif:"):
        # Явный формат: notif:NOTIFICATION_ID:CHOICE
        parts = text.split(":")
        if len(parts) == 3:
            try:
                notif_id = int(parts[1])
                choice = int(parts[2])
            except ValueError:
                pass
    elif text.isdigit() and int(text) in [1, 2, 3]:
        choice = int(text)
        # Найти последнее pending уведомление
        notif_id = await _get_last_pending_notification()

    if choice is None or notif_id is None:
        await _send_tg_message(
            chat_id,
            "❓ Не понял ответ.\n"
            "Отправь: 1, 2 или 3\n"
            "Или явно: notif:ID:CHOICE"
        )
        return {"ok": True}

    # Применяем выбор
    from core.sleep_mode import apply_architect_choice
    result = await apply_architect_choice(notif_id, choice)

    if "error" in result:
        await _send_tg_message(chat_id, f"❌ Ошибка: {result['error']}")
    else:
        await _send_tg_message(
            chat_id,
            f"✅ Применено: {result.get('description', 'OK')}"
        )

    return {"ok": True}


async def _get_last_pending_notification() -> int | None:
    """Находит последнее непринятое уведомление."""
    from db.pg_client import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM evo_notifications WHERE status='pending' ORDER BY created_at DESC LIMIT 1"
        )
    return row['id'] if row else None


async def _send_tg_message(chat_id: str, text: str):
    """Отправляет сообщение в Telegram."""
    import httpx, os
    token = os.getenv("TG_BOT_TOKEN", "")
    if not token or not chat_id:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10
            )
    except Exception as e:
        log.warning(f"[TG] Send failed: {e}")


@router.post("/tg/setup")
async def setup_tg_webhook(request: Request):
    """
    Автонастройка Telegram webhook.
    POST /api/v1/tg/setup с X-Admin-Token.
    Регистрирует /api/v1/tg/webhook в Telegram API.
    """
    from api.routes.admin import _check_admin
    token_header = request.headers.get("X-Admin-Token", "")
    _check_admin(token_header)

    from core.config_manager import get
    import httpx
    tg_token = await get("TG_BOT_TOKEN")
    tg_secret = os.getenv("TG_WEBHOOK_SECRET", "evo_tg_secret_" + os.getenv("EVO_HMAC_SECRET", "")[:8])

    # Определяем внешний URL сервера
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    server_url = body.get("server_url", os.getenv("EVO_SERVER_URL", ""))

    if not server_url:
        return {"error": "Укажи server_url в теле запроса или EVO_SERVER_URL в .env"}

    webhook_url = f"{server_url}/api/v1/tg/webhook"

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.telegram.org/bot{tg_token}/setWebhook",
            json={
                "url": webhook_url,
                "secret_token": tg_secret,
                "allowed_updates": ["message"]
            }
        )
        result = r.json()

    if result.get("ok"):
        # Сохраняем секрет
        await get.__module__ and None  # just a reference check
        import os as _os
        _os.environ["TG_WEBHOOK_SECRET"] = tg_secret
        log.info(f"[TG] Webhook установлен: {webhook_url}")
        return {"status": "ok", "webhook_url": webhook_url, "tg_response": result}
    else:
        return {"status": "error", "tg_response": result}
