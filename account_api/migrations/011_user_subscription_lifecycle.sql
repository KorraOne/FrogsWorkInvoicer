-- Add subscription lifecycle columns on users (run once on existing D1).
-- Skip any statement that errors with "duplicate column name".

ALTER TABLE users ADD COLUMN subscribed_at TEXT;
ALTER TABLE users ADD COLUMN cancel_scheduled_at TEXT;
ALTER TABLE users ADD COLUMN unsubscribed_at TEXT;
ALTER TABLE users ADD COLUMN resubscribed_at TEXT;
ALTER TABLE users ADD COLUMN plan_interval TEXT;
