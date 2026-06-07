-- Фаза Security: пользователи, API ключи, шифрование, audit log

-- Расширение для шифрования
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Пользователи и API ключи
CREATE TABLE IF NOT EXISTS evo_users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    api_key     TEXT UNIQUE NOT NULL DEFAULT encode(gen_random_bytes(32), 'hex'),
    plan        TEXT DEFAULT 'free',     -- free | pro | enterprise
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_seen   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS users_api_key_idx ON evo_users (api_key);

-- Сессии флагманов
CREATE TABLE IF NOT EXISTS evo_sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     UUID REFERENCES evo_users(id),
    flagship_id TEXT NOT NULL,
    hmac_key    TEXT NOT NULL,    -- сессионный ключ для подписи
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    expires_at  TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours',
    is_active   BOOLEAN DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON evo_sessions (user_id);

-- Audit log всех изменений конфигов
CREATE TABLE IF NOT EXISTS evo_audit_log (
    id          SERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ DEFAULT NOW(),
    action      TEXT NOT NULL,        -- "config_set" | "shard_write" | "symbol_create"
    actor       TEXT NOT NULL,        -- user_id или "system"
    target      TEXT NOT NULL,        -- ключ конфига, symbol_id и т.д.
    value_hash  TEXT,                 -- SHA-256 от нового значения (не само значение)
    ip          TEXT
);
CREATE INDEX IF NOT EXISTS audit_ts_idx ON evo_audit_log (ts DESC);

-- Шифруем sensitive поля в evo_config
-- Добавляем флаг encrypted
ALTER TABLE evo_config ADD COLUMN IF NOT EXISTS encrypted BOOLEAN DEFAULT FALSE;

-- Функция для шифрования (вызывать при записи sensitive ключей)
CREATE OR REPLACE FUNCTION encrypt_config_value(val TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN encode(
        pgp_sym_encrypt(val, current_setting('app.encryption_key', TRUE)),
        'base64'
    );
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION decrypt_config_value(val TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN pgp_sym_decrypt(
        decode(val, 'base64'),
        current_setting('app.encryption_key', TRUE)
    );
END;
$$ LANGUAGE plpgsql;

-- Rate limiting статистика
CREATE TABLE IF NOT EXISTS evo_rate_stats (
    ip_or_key   TEXT NOT NULL,
    window_ts   TIMESTAMPTZ NOT NULL,
    req_count   INTEGER DEFAULT 0,
    PRIMARY KEY (ip_or_key, window_ts)
);
