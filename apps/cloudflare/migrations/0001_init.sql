-- Atlas Research (Cloudflare edition) schema
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  question TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  report TEXT,
  model TEXT,
  tokens INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  title TEXT,
  snippet TEXT
);

CREATE INDEX IF NOT EXISTS idx_sources_run ON sources(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
