-- Миграция 007: универсальность/условность решений + защита фундаментальных знаний
-- Связана с: db/models.py, core/archivist.py, core/librarian.py, core/sleep_mode.py
--
-- Реализует явное разделение из требований Архитектора:
--   1. Решения в ядре ДОЛЖНЫ БЫТЬ универсальными для всех пользователей.
--      Частные случаи (под конкретного агента/пользователя) НЕ подмешиваются
--      в общую выдачу — хранятся отдельно с явным context_conditions.
--   2. Фундаментальные знания (не зависящие от технологий, либо для которых
--      пока не найдено решение лучше) защищены от автоочистки по рейтингу —
--      держим минимум 3-5 версий даже при низком R_f.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='scl_symbols' AND column_name='is_universal'
    ) THEN
        ALTER TABLE scl_symbols ADD COLUMN is_universal BOOLEAN DEFAULT TRUE;
        ALTER TABLE scl_symbols ADD COLUMN context_conditions TEXT;
        ALTER TABLE scl_symbols ADD COLUMN is_fundamental BOOLEAN DEFAULT FALSE;
        ALTER TABLE scl_symbols ADD COLUMN last_tech_check TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- Индекс для быстрой фильтрации в librarian.find_symbols (по умолчанию
-- выдаём только is_universal=TRUE — условные решения не просачиваются
-- в чужие картриджи)
CREATE INDEX IF NOT EXISTS scl_universal_idx
    ON scl_symbols (is_universal)
    WHERE is_universal = TRUE AND is_legacy = FALSE;

-- Индекс для сканера очистки (sleep_mode._prune_outdated_knowledge):
-- находит кандидатов на архивацию — низкий рейтинг, давно не обновлялись,
-- НЕ фундаментальные
CREATE INDEX IF NOT EXISTS scl_prune_candidates_idx
    ON scl_symbols (rating_frequency, last_updated)
    WHERE is_fundamental = FALSE AND is_legacy = FALSE;
