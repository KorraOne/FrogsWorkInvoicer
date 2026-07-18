-- Analytics rebuild: drop outdated admin/user-test/promo tables;
-- add account device registry.

DROP TABLE IF EXISTS user_test_submissions;
DROP TABLE IF EXISTS user_test_settings;
DROP TABLE IF EXISTS checkout_promo_settings;

CREATE TABLE IF NOT EXISTS account_devices (
  user_id INTEGER NOT NULL,
  device_id_hash TEXT NOT NULL,
  platform TEXT NOT NULL,
  coarse_ua TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  PRIMARY KEY (user_id, device_id_hash),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_account_devices_platform ON account_devices(platform);
CREATE INDEX IF NOT EXISTS idx_account_devices_last_seen ON account_devices(last_seen_at);
