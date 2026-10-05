-- 001: Application schema and migration tracking table.
--
-- Everything the application layer creates lives in the `app` schema.
-- Nothing in `public` (raw country tables, legacy views) is altered.

CREATE SCHEMA app;

COMMENT ON SCHEMA app IS
    'Application read model built from the raw public.youtube_trending_* tables. Raw tables are never modified.';

CREATE TABLE app.schema_migrations (
    version     text        PRIMARY KEY,           -- e.g. '001'
    filename    text        NOT NULL,              -- e.g. '001_app_schema.sql'
    checksum    text        NOT NULL,              -- sha256 of the file contents
    applied_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE app.schema_migrations IS
    'Numbered SQL migrations applied by backend/scripts/migrate.py.';
