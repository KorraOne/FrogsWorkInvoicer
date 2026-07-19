-- Payment follow-up emails: purpose + schedule_key for idempotent reminders

ALTER TABLE email_outbox ADD COLUMN purpose TEXT NOT NULL DEFAULT 'initial';
ALTER TABLE email_outbox ADD COLUMN schedule_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_outbox_reminder_unique
  ON email_outbox(user_id, invoice_key, purpose, schedule_key)
  WHERE purpose = 'payment_reminder';
