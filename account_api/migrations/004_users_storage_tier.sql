-- Safe for DBs created before cloud documents (003). Idempotent: ignore if column exists.
ALTER TABLE users ADD COLUMN storage_tier TEXT NOT NULL DEFAULT 'local';
