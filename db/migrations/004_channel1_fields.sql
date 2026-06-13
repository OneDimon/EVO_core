-- Миграция 004: Канал 1 — поля автономного сбора знаний
-- Применяется поверх существующей scl_symbols таблицы
-- Созданы: knowledge_collector.py, SLEEP_MODE.md v1.1
-- Связана с: db/models.py SCLSymbol, db/pg_client.py insert_symbol

-- Добавляем поля Канала 1 (IF NOT EXISTS — безопасно запускать повторно)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='scl_symbols' AND column_name='source_url'
    ) THEN
        ALTER TABLE scl_symbols ADD COLUMN source_url     TEXT;
        ALTER TABLE scl_symbols ADD COLUMN source_rating  INTEGER DEFAULT 0;
        ALTER TABLE scl_symbols ADD COLUMN source_type    TEXT;
        ALTER TABLE scl_symbols ADD COLUMN auto_collected BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Индекс для выборки автособранных символов (нужен для отчётов sleep_mode)
CREATE INDEX IF NOT EXISTS scl_auto_collected_idx
    ON scl_symbols (auto_collected, last_updated)
    WHERE auto_collected = TRUE;

-- Индекс для фильтрации по типу источника
CREATE INDEX IF NOT EXISTS scl_source_type_idx
    ON scl_symbols (source_type)
    WHERE source_type IS NOT NULL;
