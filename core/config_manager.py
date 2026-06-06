"""
Config Manager — единое место хранения всех токенов и конфигов.
Читает из БД (таблица evo_config) + .env как fallback.
Пишется через Admin API — один раз, применяется везде автоматически.
"""
import os, json, logging
from db.pg_client import get_pool

log = logging.getLogger("evo.config")
_cache: dict = {}


async def init_config_table():
    """Создаёт таблицу конфигов если не существует."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS evo_config (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                description TEXT,
                category    TEXT DEFAULT 'general',
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)


async def get(key: str, default: str = "") -> str:
    """Читает значение: БД → .env → default."""
    if key in _cache:
        return _cache[key]
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM evo_config WHERE key=$1", key)
    if row:
        _cache[key] = row['value']
        return row['value']
    env_val = os.getenv(key, default)
    return env_val


async def set(key: str, value: str, description: str = "", category: str = "general"):
    """Сохраняет значение в БД + обновляет кэш."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO evo_config (key, value, description, category, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (key) DO UPDATE SET value=$2, updated_at=NOW()
        """, key, value, description, category)
    _cache[key] = value
    log.info(f"[Config] {key} обновлён")


async def get_all(category: str = None) -> list[dict]:
    """Возвращает все настройки (для Admin UI)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if category:
            rows = await conn.fetch(
                "SELECT key,value,description,category,updated_at FROM evo_config WHERE category=$1 ORDER BY key",
                category
            )
        else:
            rows = await conn.fetch(
                "SELECT key,value,description,category,updated_at FROM evo_config ORDER BY category,key"
            )
    # Маскируем секреты
    result = []
    for r in rows:
        val = r['value']
        if any(s in r['key'].upper() for s in ['TOKEN','SECRET','KEY','PASSWORD']):
            val = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
        result.append({"key": r['key'], "value": val,
                        "description": r['description'], "category": r['category']})
    return result


# ── Ключи конфигурации ────────────────────────────────────────────────────────
# Все значения вносятся ОДИН РАЗ в Admin UI → применяются везде автоматически

CONFIG_SCHEMA = {
    # Уведомления
    "TG_BOT_TOKEN":         ("telegram", "Telegram Bot Token для уведомлений Архитектора"),
    "TG_ADMIN_CHAT_ID":     ("telegram", "Chat ID Архитектора в Telegram"),
    "ADMIN_NOTIFY_URL":     ("telegram", "URL endpoint админки для уведомлений"),

    # Шарды — бесплатные облака
    "SHARD_PRIMARY_HOST":   ("shards", "Основной шард (Google Drive / Mega / R2 hostname)"),
    "SHARD_MIRROR_HOST":    ("shards", "Зеркало шарда"),
    "SHARD_PROVIDER":       ("shards", "Провайдер: gdrive | mega | r2 | github | local"),
    "SHARD_GDRIVE_TOKEN":   ("shards", "Google Drive API token"),
    "SHARD_GDRIVE_FOLDER":  ("shards", "Google Drive Folder ID"),
    "SHARD_GITHUB_TOKEN":   ("shards", "GitHub token для хранения ячеек в репо"),
    "SHARD_GITHUB_REPO":    ("shards", "GitHub repo для шардов: owner/repo"),
    "SHARD_R2_ACCOUNT_ID":  ("shards", "Cloudflare R2 Account ID"),
    "SHARD_R2_ACCESS_KEY":  ("shards", "Cloudflare R2 Access Key"),
    "SHARD_R2_SECRET_KEY":  ("shards", "Cloudflare R2 Secret Key"),
    "SHARD_R2_BUCKET":      ("shards", "Cloudflare R2 Bucket name"),

    # AI Router
    "GEMINI_API_KEY":       ("ai", "Google Gemini API Key (primary model)"),
    "OPENAI_API_KEY":       ("ai", "OpenAI API Key (optional fallback)"),
    "OLLAMA_HOST":          ("ai", "Ollama host (default: http://localhost:11434)"),

    # Безопасность
    "EVO_HMAC_SECRET":      ("security", "HMAC секрет для подписи ответов ядра"),
    "EVO_API_SECRET":       ("security", "API секрет для авторизации запросов"),
}
