CREATE TABLE IF NOT EXISTS checkout_promo_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  default_beta80_enabled INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO checkout_promo_settings (id, default_beta80_enabled, updated_at)
  VALUES (1, 0, datetime('now'));
