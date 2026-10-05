#!/bin/sh
# Database tool commands for the Compose deployment (see DEPLOYMENT.md).
# Credentials come from the environment only (docker compose passes them from .env).
set -eu

: "${DB_HOST:?}" "${DB_NAME:?}" "${DB_USER:?}" "${DB_PASSWORD:?}"
export PGHOST="$DB_HOST" PGPORT="${DB_PORT:-5432}" PGDATABASE="$DB_NAME" PGUSER="$DB_USER"
export PGPASSWORD="$DB_PASSWORD"

RAW_TABLES="au ca gb ie in nz sg us za"
DUMP="${SEED_DUMP:-/seed/raw_tables.dump}"

raw_tables_present() {
  psql -XAtq -v ON_ERROR_STOP=1 -c \
    "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'youtube_trending\___'"
}

case "${1:-status}" in
  seed)
    # Never overwrites: refuses unless the database has none of the raw tables yet, and
    # restores in ONE transaction (all tables or nothing).
    [ -r "$DUMP" ] || { echo "error: seed dump not found at $DUMP (see DEPLOYMENT.md)" >&2; exit 1; }
    present="$(raw_tables_present)"
    if [ "$present" != "0" ]; then
      echo "error: $present raw youtube_trending_* tables already exist; refusing to seed." >&2
      exit 1
    fi
    echo "restoring raw tables from $DUMP (single transaction) ..."
    pg_restore --no-owner --no-privileges --single-transaction --exit-on-error -d "$DB_NAME" "$DUMP"
    for t in $RAW_TABLES; do
      psql -XAtq -v ON_ERROR_STOP=1 -c "ANALYZE public.youtube_trending_$t"
    done
    echo "seeded: $(raw_tables_present) raw tables"
    ;;
  migrate)
    python3 backend/scripts/migrate.py apply
    python3 backend/scripts/migrate.py set-app-role-password
    python3 backend/scripts/migrate.py set-auth-role-password
    python3 backend/scripts/migrate.py status
    ;;
  status)
    python3 backend/scripts/migrate.py status
    ;;
  *)
    echo "usage: dbtools {seed|migrate|status}" >&2
    exit 2
    ;;
esac
