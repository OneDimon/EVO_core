-- Миграция 005: evo_sessions — сессии флагманов (HMAC-рукопожатие)
-- Связана с: api/routes/handshake.py, api/middleware/security.py
-- P5 fix: таблица отсутствовала во всех предыдущих миграциях

CREATE TABLE IF NOT EXISTS evo_sessions (
    session_id   TEXT PRIMARY KEY,
    flagship_id  TEXT NOT NULL,
    hmac_key     TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    last_active  TIMESTAMPTZ DEFAULT NOW(),
    meta         JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS evo_sessions_created_idx
    ON evo_sessions (created_at);

CREATE INDEX IF NOT EXISTS evo_sessions_flagship_idx
    ON evo_sessions (flagship_id);

-- Автоочистка сессий старше 24 часов (вызывать из sleep_mode задача 3)
-- DELETE FROM evo_sessions WHERE created_at < NOW() - INTERVAL '24 hours';
