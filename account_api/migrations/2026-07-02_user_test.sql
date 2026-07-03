-- User testing intake (apply once to remote D1)
CREATE TABLE IF NOT EXISTS user_test_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  enabled INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO user_test_settings (id, enabled, updated_at)
  VALUES (1, 0, datetime('now'));

CREATE TABLE IF NOT EXISTS user_test_submissions (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  completed_at TEXT,
  tester_name TEXT,
  answers_json TEXT,
  video_r2_key TEXT,
  video_bytes INTEGER,
  video_content_type TEXT,
  client_ip_hash TEXT,
  status TEXT NOT NULL DEFAULT 'pending_upload'
);

CREATE INDEX IF NOT EXISTS idx_user_test_submissions_created
  ON user_test_submissions(created_at);

CREATE INDEX IF NOT EXISTS idx_user_test_submissions_ip_created
  ON user_test_submissions(client_ip_hash, created_at);
