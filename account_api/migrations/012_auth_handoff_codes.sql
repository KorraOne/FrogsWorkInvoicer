CREATE TABLE IF NOT EXISTS auth_handoff_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code_hash TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  used_at TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_auth_handoff_codes_hash
  ON auth_handoff_codes(code_hash);

CREATE INDEX IF NOT EXISTS idx_auth_handoff_codes_expires
  ON auth_handoff_codes(expires_at);
