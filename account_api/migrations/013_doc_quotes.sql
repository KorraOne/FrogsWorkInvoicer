-- Quotes / price estimates (parallel to doc_invoices) + email outbox doc_type

CREATE TABLE IF NOT EXISTS doc_quotes (
  user_id INTEGER NOT NULL,
  quote_key TEXT NOT NULL,
  quote_number INTEGER NOT NULL,
  data_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  pdf_status TEXT NOT NULL DEFAULT 'pending',
  pdf_r2_key TEXT,
  PRIMARY KEY (user_id, quote_key),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_doc_quotes_user_number
  ON doc_quotes(user_id, quote_number);

-- D1/SQLite: ADD COLUMN fails if the column already exists; migrations run once.
ALTER TABLE email_outbox ADD COLUMN doc_type TEXT NOT NULL DEFAULT 'invoice';
