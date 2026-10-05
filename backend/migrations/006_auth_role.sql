-- 006: Role yt_auth_rw for authentication writes.
--
-- Least privilege: read/write on the `auth` tables only. No access to `app` (analytics) or
-- `public` (raw data). Analytics keep using the read-only role yt_app_ro, which gets no
-- access to `auth`. Created WITHOUT a password; set it with
--   python backend/scripts/migrate.py set-auth-role-password   (reads DB_AUTH_PASSWORD)
--
-- Rollback (manual): REVOKE ALL ON ALL TABLES IN SCHEMA auth FROM yt_auth_rw;
--   REVOKE USAGE ON SCHEMA auth FROM yt_auth_rw; DROP ROLE yt_auth_rw;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'yt_auth_rw') THEN
        CREATE ROLE yt_auth_rw
            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS
            CONNECTION LIMIT 20;
    END IF;
END
$$;

ALTER ROLE yt_auth_rw SET statement_timeout = '5s';

GRANT USAGE ON SCHEMA auth TO yt_auth_rw;
GRANT SELECT, INSERT, UPDATE ON auth.tenants, auth.users, auth.memberships TO yt_auth_rw;
GRANT SELECT, INSERT, DELETE ON auth.sessions TO yt_auth_rw;
