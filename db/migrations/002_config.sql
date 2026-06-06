CREATE TABLE IF NOT EXISTS evo_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT DEFAULT '',
    category    TEXT DEFAULT 'general',
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO evo_config (key, value, description, category) VALUES
    ('SHARD_PROVIDER', 'local', 'Провайдер: local|gdrive|github|r2', 'shards'),
    ('SHARD_PRIMARY_HOST', '', 'Основной хост шарда', 'shards'),
    ('SHARD_MIRROR_HOST',  '', 'Зеркало шарда', 'shards'),
    ('OLLAMA_HOST', 'http://localhost:11434', 'Ollama host', 'ai')
ON CONFLICT (key) DO NOTHING;
