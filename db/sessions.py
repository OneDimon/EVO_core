"""
Sessions — сессии флагманов.
Таблица evo_sessions (миграция 003_users_security.sql: session_id PK,
user_id, flagship_id, hmac_key, created_at, expires_at, is_active).
Запись создаётся в api/routes/handshake.py при подключении флагмана.
"""
import logging
from db.pg_client import get_pool

log = logging.getLogger("evo.sessions")


async def get_session(session_id: str) -> dict | None:
    """
    Возвращает сессию по session_id или None если не найдена.
    Используется core/signature.py для получения hmac_key при
    подписи/верификации evo_signature.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT session_id, flagship_id, hmac_key, is_active, "
            "created_at, expires_at FROM evo_sessions WHERE session_id = $1",
            session_id
        )
    return dict(row) if row else None
