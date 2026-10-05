-- 004: Read-only application role yt_app_ro.
--
-- SELECT on the two application views only. No access to app.schema_migrations
-- and no grants on any public raw table or legacy view.
-- Grants are per object (no ALTER DEFAULT PRIVILEGES), so future app objects are
-- not exposed automatically.
--
-- The role is created WITHOUT a password, so it cannot log in until one is set
-- with `python backend/scripts/migrate.py set-app-role-password` (reads
-- DB_APP_RO_PASSWORD from .env). No credential appears in this file.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'yt_app_ro') THEN
        CREATE ROLE yt_app_ro
            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS
            CONNECTION LIMIT 20;
    END IF;
END
$$;

-- Defence in depth: every session of this role is read-only by default.
ALTER ROLE yt_app_ro SET default_transaction_read_only = on;

-- CONNECT is intentionally not granted here: the database's default PUBLIC
-- CONNECT privilege is relied on, so this migration only touches app-specific
-- permissions.

GRANT USAGE ON SCHEMA app TO yt_app_ro;
GRANT SELECT ON app.trending_snapshots, app.video_details TO yt_app_ro;
