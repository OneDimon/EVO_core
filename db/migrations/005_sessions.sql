-- Миграция 005: дополнение evo_sessions индексами (таблица создана в 003)
-- N1 fix: 003_users_security.sql уже создаёт evo_sessions с полной схемой.
-- Эта миграция только добавляет недостающие индексы.
-- Схема из 003: session_id PK, user_id UUID REF evo_users,
--               flagship_id TEXT, hmac_key TEXT,
--               created_at, expires_at, is_active BOOLEAN

-- Индекс по flagship_id (для поиска сессий по флагману)
CREATE INDEX IF NOT EXISTS evo_sessions_flagship_idx
    ON evo_sessions (flagship_id);

-- Индекс по is_active (для быстрой выборки активных сессий)
CREATE INDEX IF NOT EXISTS evo_sessions_active_idx
    ON evo_sessions (is_active)
    WHERE is_active = TRUE;

-- Очистка просроченных сессий (вызывается из sleep_mode задача 3):
-- DELETE FROM evo_sessions WHERE expires_at < NOW();
