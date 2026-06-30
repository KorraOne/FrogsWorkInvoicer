CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  stripe_customer_id TEXT,
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
