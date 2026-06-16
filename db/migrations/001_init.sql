CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS scl_symbols (
    id                TEXT PRIMARY KEY,
    label             TEXT NOT NULL,
    vector            vector(768),
    science           TEXT NOT NULL,
    section           TEXT NOT NULL,
    subsection        TEXT NOT NULL,
    rating_frequency  INTEGER DEFAULT 0,
    confirmed_by      INTEGER DEFAULT 1,
    confirmed_in      TEXT[] DEFAULT '{}',
    evolved_from      TEXT REFERENCES scl_symbols(id),
    evolution_note    TEXT,
    last_updated      TIMESTAMPTZ DEFAULT NOW(),
    shard_host        TEXT NOT NULL DEFAULT '',
    shard_path        TEXT NOT NULL DEFAULT '',
    shard_mirror      TEXT,
    legacy_symbols    TEXT[] DEFAULT '{}',
    applicable_stacks TEXT[] DEFAULT '{}',
    hyperlinks        TEXT[] DEFAULT '{}',
    is_legacy         BOOLEAN DEFAULT FALSE,
    superseded_by     TEXT,
    supersedes        TEXT,
    hypothesis        BOOLEAN DEFAULT FALSE,
    source_url        TEXT,                       -- URL источника (Канал 1)
    source_rating     INTEGER DEFAULT 0,           -- stars/downloads источника
    source_type       TEXT,                        -- github|npm|pypi|n8n|official|cli_plugin
    auto_collected    BOOLEAN DEFAULT FALSE,        -- собрано автономно (Канал 1)
    version_ts        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS scl_vector_idx ON scl_symbols
  USING ivfflat (vector vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS scl_class_idx  ON scl_symbols (science, section, subsection);
CREATE INDEX IF NOT EXISTS scl_rating_idx ON scl_symbols (rating_frequency DESC);
CREATE INDEX IF NOT EXISTS scl_stacks_idx ON scl_symbols USING gin (applicable_stacks);
CREATE INDEX IF NOT EXISTS scl_conf_idx   ON scl_symbols USING gin (confirmed_in);
CREATE INDEX IF NOT EXISTS scl_legacy_idx ON scl_symbols (is_legacy, superseded_by);
CREATE INDEX IF NOT EXISTS scl_hypo_idx   ON scl_symbols (hypothesis, last_updated);

CREATE TABLE IF NOT EXISTS evo_rps_stats (
    hour_ts     TIMESTAMPTZ NOT NULL,
    rps         FLOAT NOT NULL,
    session_cnt INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS rps_hour_idx ON evo_rps_stats (hour_ts DESC);

CREATE TABLE IF NOT EXISTS evo_notifications (
    id          SERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    zone        TEXT NOT NULL,
    problem     TEXT NOT NULL,
    options     JSONB NOT NULL,
    status      TEXT DEFAULT 'pending',
    chosen      INTEGER
);

-- P13 fix: индекс для быстрой выборки pending уведомлений
CREATE INDEX IF NOT EXISTS evo_notif_status_idx
    ON evo_notifications (status)
    WHERE status = 'pending';
