-- Per-IP / global daily request caps (denial-of-wallet protection)
CREATE TABLE IF NOT EXISTS rate_limits (
  ip TEXT NOT NULL,
  day TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (ip, day)
);
