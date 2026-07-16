-- Resolve email outbox rows when invoice_key is a UUID (display number may be reused).
ALTER TABLE email_outbox ADD COLUMN invoice_key TEXT;
CREATE INDEX IF NOT EXISTS idx_email_outbox_invoice_key ON email_outbox(invoice_key);
