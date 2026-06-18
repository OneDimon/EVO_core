"""
Users — управление пользователями и API ключами.
Таблица evo_users (миграция 003_users_security.sql).
"""
import secrets, logging
from db.pg_client import get_pool

log = logging.getLogger("evo.users")


async def create_user(email: str, plan: str = "free") -> dict:
    """
    Создаёт пользователя, возвращает API ключ.
    N3 fix: при конфликте email — возвращает существующий ключ из БД.
    Ранее: ON CONFLICT DO UPDATE SET plan=$3 + RETURNING api_key
    возвращал новый несохранённый ключ ($2) → пользователь получал
    ключ которого нет в БД → 403 при всех запросах.
    """
    api_key = secrets.token_hex(32)
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Сначала пробуем вставить нового пользователя
        row = await conn.fetchrow("""
            INSERT INTO evo_users (email, api_key, plan)
            VALUES ($1, $2, $3)
            ON CONFLICT (email) DO NOTHING
            RETURNING id, email, api_key, plan, created_at
        """, email, api_key, plan)

        if row is None:
            # Пользователь уже существует — возвращаем существующий ключ
            # Обновляем план если передан новый
            row = await conn.fetchrow("""
                UPDATE evo_users SET plan=$2
                WHERE email=$1
                RETURNING id, email, api_key, plan, created_at
            """, email, plan)
            log.info(f"[Users] Существующий пользователь: {email}, план обновлён до {plan}")
        else:
            log.info(f"[Users] Новый пользователь: {email} plan={plan}")

    return dict(row)


async def get_user_by_key(api_key: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM evo_users WHERE api_key=$1 AND is_active=TRUE",
            api_key
        )
    return dict(row) if row else None


async def rotate_api_key(user_id: str) -> str:
    """Генерирует новый API ключ для пользователя."""
    new_key = secrets.token_hex(32)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE evo_users SET api_key=$2 WHERE id=$1",
            user_id, new_key
        )
    log.info(f"[Users] Ключ ротирован для {user_id}")
    return new_key


async def deactivate_user(user_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE evo_users SET is_active=FALSE WHERE id=$1", user_id
        )
    log.info(f"[Users] Деактивирован: {user_id}")
