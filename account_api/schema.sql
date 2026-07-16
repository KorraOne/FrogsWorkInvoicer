CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  stripe_customer_id TEXT,
  storage_tier TEXT NOT NULL DEFAULT 'local',
  account_status TEXT NOT NULL DEFAULT 'active',
  email_verified_at TEXT,
  install_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS installs (
  install_id TEXT PRIMARY KEY,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  first_invoice_at TEXT,
  first_customer_at TEXT,
  first_invoice_sent_at TEXT,
  first_paid_marked_at TEXT,
  account_created_at TEXT,
  user_id INTEGER,
  subscribed_at TEXT,
  cancel_scheduled_at TEXT,
  unsubscribed_at TEXT,
  resubscribed_at TEXT,
  uninstalled_at TEXT,
  subscription_state TEXT NOT NULL DEFAULT 'none',
  signup_invoice_count INTEGER,
  signup_ex_gst TEXT,
  signup_gst_registered INTEGER,
  subscribe_invoice_count INTEGER,
  subscribe_ex_gst TEXT,
  trial_gate_hit TEXT,
  plan_interval TEXT,
  customer_count INTEGER,
  business_count INTEGER,
  invoices_sent INTEGER,
  invoices_paid INTEGER,
  invoices_not_sent INTEGER,
  due_rule_type TEXT,
  custom_pdf_folder INTEGER,
  gst_registered INTEGER,
  welcome_complete INTEGER,
  lifetime_invoice_count INTEGER,
  lifetime_ex_gst TEXT,
  days_since_last_invoice INTEGER,
  has_backup_export INTEGER NOT NULL DEFAULT 0,
  has_backup_import INTEGER NOT NULL DEFAULT 0,
  app_version_first TEXT,
  app_version_last TEXT,
  is_packaged INTEGER,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_installs_user_id ON installs(user_id);
CREATE INDEX IF NOT EXISTS idx_installs_last_seen ON installs(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_users_install_id ON users(install_id);

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

CREATE TABLE IF NOT EXISTS doc_businesses (
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  data_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, name),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS doc_customers (
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  data_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, name),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS doc_invoices (
  user_id INTEGER NOT NULL,
  invoice_key TEXT NOT NULL,
  invoice_number INTEGER NOT NULL,
  data_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  pdf_status TEXT NOT NULL DEFAULT 'pending',
  pdf_r2_key TEXT,
  PRIMARY KEY (user_id, invoice_key),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_doc_invoices_user_number
  ON doc_invoices(user_id, invoice_number);

CREATE TABLE IF NOT EXISTS guest_workspaces (
  guest_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  data_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS email_outbox (
  id TEXT PRIMARY KEY,
  user_id INTEGER,
  guest_id TEXT,
  invoice_number INTEGER NOT NULL,
  invoice_key TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_email_outbox_status ON email_outbox(status);
CREATE INDEX IF NOT EXISTS idx_email_outbox_invoice_key ON email_outbox(invoice_key);

CREATE TABLE IF NOT EXISTS doc_settings (
  user_id INTEGER PRIMARY KEY,
  data_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS checkout_promo_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  default_beta80_enabled INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO checkout_promo_settings (id, default_beta80_enabled, updated_at)
  VALUES (1, 0, datetime('now'));

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash
  ON password_reset_tokens(token_hash);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_hash
  ON email_verification_tokens(token_hash);

CREATE TABLE IF NOT EXISTS rate_limit_buckets (
  bucket_key TEXT PRIMARY KEY,
  window_start TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0
);
