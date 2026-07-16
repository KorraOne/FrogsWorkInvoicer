-- Idempotent: guest trial + cloud doc tables (skip storage_tier ALTER if 004 already applied)

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
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_email_outbox_status ON email_outbox(status);

CREATE TABLE IF NOT EXISTS doc_settings (
  user_id INTEGER PRIMARY KEY,
  data_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
