-- Migration 009: множественные API-ключи + лог метрик запросов
--
-- Обоснование (см. аудит от 2026-07-31): личный кабинет требует, чтобы
-- пользователь мог создавать/удалять СВОИ API-ключи — текущая схема
-- (evo_users.api_key, один ключ на пользователя, только ротация через
-- админа) этого не позволяет. И админ-панели владельца, и личному кабинету
-- пользователя нужна статистика скорости/токенов по каждому запросу —
-- такого лога в схеме не было вообще.

-- ── Множественные API-ключи ──────────────────────────────────────────────
-- Сырой ключ НИГДЕ не хранится — только SHA-256 хэш (проверяется на входе
-- пересчётом хэша) и 8-символьный префикс сырого ключа для отображения в
-- UI ("sk_a1b2****"), без возможности восстановить ключ целиком из БД.
CREATE TABLE IF NOT EXISTS evo_api_keys (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES evo_users(id) ON DELETE CASCADE,
    key_hash      TEXT UNIQUE NOT NULL,
    prefix        TEXT NOT NULL,
    label         TEXT NOT NULL DEFAULT 'API ключ',
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    last_used_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS api_keys_user_idx ON evo_api_keys (user_id);
CREATE INDEX IF NOT EXISTS api_keys_hash_idx ON evo_api_keys (key_hash);

-- ── Лог запросов — источник метрик для обеих админок ────────────────────
-- Правило Архитектора: НЕ хранит содержимое пользовательских проектов
-- или решений (ни текст запроса, ни ответ) — только метаданные обращения:
-- кто, куда, за сколько, с каким статусом, сколько токенов.
CREATE TABLE IF NOT EXISTS evo_request_log (
    id                   BIGSERIAL PRIMARY KEY,
    ts                   TIMESTAMPTZ DEFAULT NOW(),
    user_id              UUID REFERENCES evo_users(id),
    api_key_id           UUID REFERENCES evo_api_keys(id),
    session_id           TEXT,
    endpoint             TEXT NOT NULL,
    status               TEXT NOT NULL,          -- 'ok' | 'error'
    error_type           TEXT,
    latency_ms           INTEGER NOT NULL,
    tokens_actual        INTEGER DEFAULT 0,       -- реально потрачено ядром (эмбеддинг/классификация)
    tokens_baseline_est  INTEGER DEFAULT 0        -- оценка: сколько потратил бы флагман, генерируя это сам
);
CREATE INDEX IF NOT EXISTS request_log_user_ts_idx ON evo_request_log (user_id, ts DESC);
CREATE INDEX IF NOT EXISTS request_log_ts_idx ON evo_request_log (ts DESC);
CREATE INDEX IF NOT EXISTS request_log_error_idx ON evo_request_log (ts DESC) WHERE status = 'error';
