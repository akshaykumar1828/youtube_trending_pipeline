-- 005: Authentication, tenants and tenant-scoped roles (schema `auth`).
--
-- Tenant-owned data lives here. The YouTube analytics read model (`app`) and the raw
-- tables (`public`) are shared, global and read-only; they are not altered and are not
-- duplicated per tenant.
--
-- Rollback (manual, destroys auth data only):
--   DROP SCHEMA auth CASCADE; DELETE FROM app.schema_migrations WHERE version = '005';

CREATE SCHEMA auth;

COMMENT ON SCHEMA auth IS
    'Users, tenants, tenant memberships (roles) and login sessions. Tenant-owned data.';

CREATE TABLE auth.tenants (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text        NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 100),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auth.users (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    email               text        NOT NULL CHECK (email = lower(email) AND length(email) BETWEEN 3 AND 254),
    display_name        text        NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 100),
    password_hash       text        NOT NULL CHECK (password_hash LIKE '$argon2id$%'),  -- never plaintext
    is_active           boolean     NOT NULL DEFAULT true,
    failed_login_count  integer     NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
    locked_until        timestamptz,
    last_login_at       timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Emails are stored lower-cased (CHECK above), so a plain unique index is case-insensitive.
CREATE UNIQUE INDEX users_email_key ON auth.users (email);

-- Tenant-scoped role. The role set is fixed and small; permissions are mapped in code.
CREATE TABLE auth.memberships (
    user_id     uuid        NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    tenant_id   uuid        NOT NULL REFERENCES auth.tenants (id) ON DELETE CASCADE,
    role        text        NOT NULL CHECK (role IN ('OWNER', 'ADMIN', 'MEMBER')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, tenant_id),
    -- One tenant per user for now; dropping this constraint enables multi-tenant users later.
    CONSTRAINT memberships_one_tenant_per_user UNIQUE (user_id)
);

CREATE INDEX memberships_tenant_idx ON auth.memberships (tenant_id);

-- Server-side sessions. Only a keyed hash (HMAC-SHA256) of the opaque token is stored.
-- The composite FK guarantees a session's tenant is the user's actual membership, and
-- removing the membership removes its sessions.
CREATE TABLE auth.sessions (
    token_hash  bytea       PRIMARY KEY CHECK (length(token_hash) = 32),
    user_id     uuid        NOT NULL,
    tenant_id   uuid        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    CHECK (expires_at > created_at),
    FOREIGN KEY (user_id, tenant_id) REFERENCES auth.memberships (user_id, tenant_id) ON DELETE CASCADE
);

CREATE INDEX sessions_user_idx ON auth.sessions (user_id);
CREATE INDEX sessions_expires_idx ON auth.sessions (expires_at);
