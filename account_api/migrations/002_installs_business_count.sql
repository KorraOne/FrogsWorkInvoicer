-- Adds business_count to installs (admin + telemetry). Safe on DBs created from schema after 2.1.1.
ALTER TABLE installs ADD COLUMN business_count INTEGER;
