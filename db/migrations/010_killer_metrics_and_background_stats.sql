-- Migration 010: честные проверяемые метрики для ЛК, предпочтение
-- execution_mode, статистика фоновой работы (Sleep Mode) для обеих админок.

-- ── Реальные, проверяемые киллер-метрики при выдаче ─────────────────────
-- scenario/confirmed_by/rating символа В МОМЕНТ выдачи — переживает TTL
-- Redis-плана (1 час), нужно для честных цифр в ЛК ("X% решений пришли
-- 100%-подтверждёнными с первого раза", "ваши решения проверены N раз
-- независимо другими пользователями").
ALTER TABLE evo_request_log ADD COLUMN IF NOT EXISTS scenario TEXT;
ALTER TABLE evo_request_log ADD COLUMN IF NOT EXISTS symbol_confirmed_by INTEGER;
ALTER TABLE evo_request_log ADD COLUMN IF NOT EXISTS symbol_rating INTEGER;

-- ── Предпочтение режима выполнения — личный кабинет ─────────────────────
ALTER TABLE evo_users ADD COLUMN IF NOT EXISTS default_execution_mode TEXT DEFAULT 'stepwise';

-- ── Фоновая работа ядра (Sleep Mode) — теоретическая выгода ─────────────
-- Работа Sleep Mode (актуализация, целостность, поиск лигатур) выгодна
-- ВСЕМ пользователям общей библиотеки — не привязана к одному user_id,
-- поэтому отдельная таблица, не колонка в evo_request_log. Дневной
-- роллап, не построчный лог (это фоновая статистика, не трейс запроса).
CREATE TABLE IF NOT EXISTS evo_background_stats (
    day                     DATE PRIMARY KEY,
    symbols_actualized      INTEGER DEFAULT 0,  -- _actualize_tech_currency
    ligatures_formed        INTEGER DEFAULT 0,  -- _check_ligature_candidates (obsidian)
    integrity_fixes         INTEGER DEFAULT 0,  -- _check_integrity
    tokens_saved_theoretical BIGINT DEFAULT 0    -- оценка: во сколько токенов обошлась бы
                                                  -- пользователям работа со стухшими/битыми
                                                  -- символами, если бы Sleep Mode их не нашёл
);
