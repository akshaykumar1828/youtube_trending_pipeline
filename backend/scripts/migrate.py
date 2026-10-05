"""Minimal numbered-SQL migration runner for the application schema.

Usage (from the repo root):
    python backend/scripts/migrate.py status                 # list applied / pending migrations
    python backend/scripts/migrate.py apply                  # apply pending migrations in order
    python backend/scripts/migrate.py set-app-role-password  # set yt_app_ro password from .env
    python backend/scripts/migrate.py set-auth-role-password # set yt_auth_rw password from .env

Connects as the admin user from .env (DB_USER / DB_PASSWORD) using psql.
Each migration runs in its own transaction together with its
app.schema_migrations record, so a failed migration leaves no trace.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
FILENAME_PATTERN = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
APP_ROLE = "yt_app_ro"
AUTH_ROLE = "yt_auth_rw"


def fail(message):
    sys.exit(f"error: {message}")


def psql(script):
    """Run a psql script from stdin as the admin user; return stdout."""
    load_dotenv()
    missing = [v for v in ("DB_NAME", "DB_PASSWORD") if not os.getenv(v)]
    if missing:
        fail(f"missing required environment variables: {', '.join(missing)}. See .env.example.")

    psql_bin = os.getenv("PSQL_PATH") or shutil.which("psql")
    if not psql_bin:
        fail("psql not found; add PostgreSQL's bin directory to PATH or set PSQL_PATH")

    env = {**os.environ, "PGPASSWORD": os.environ["DB_PASSWORD"], "PGCLIENTENCODING": "UTF8"}
    cmd = [
        psql_bin, "-X", "-w", "-q", "-At", "-v", "ON_ERROR_STOP=1",
        "-h", os.getenv("DB_HOST", "localhost"),
        "-p", os.getenv("DB_PORT", "5432"),
        "-U", os.getenv("DB_USER", "postgres"),
        "-d", os.environ["DB_NAME"],
    ]
    result = subprocess.run(cmd, input=script.encode("utf-8"), env=env, capture_output=True)
    if result.returncode != 0:
        fail(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout.decode("utf-8")


def migration_files():
    files = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = FILENAME_PATTERN.match(path.name)
        if not match:
            fail(f"unexpected migration filename: {path.name}")
        content = path.read_text(encoding="utf-8")
        files.append({
            "version": match.group(1),
            "filename": path.name,
            "content": content,
            "checksum": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        })
    versions = [f["version"] for f in files]
    if len(versions) != len(set(versions)):
        fail("duplicate migration version numbers")
    return files


def applied_migrations():
    out = psql(
        "SELECT CASE WHEN to_regclass('app.schema_migrations') IS NULL THEN 'none' ELSE 'exists' END;"
    ).strip()
    if out == "none":
        return {}
    rows = psql("SELECT version, checksum FROM app.schema_migrations ORDER BY version;")
    return dict(line.split("|", 1) for line in rows.splitlines() if line)


def check_integrity(files, applied):
    by_version = {f["version"]: f for f in files}
    for version, checksum in applied.items():
        if version not in by_version:
            fail(f"migration {version} is recorded as applied but its file is missing")
        if by_version[version]["checksum"] != checksum:
            fail(f"{by_version[version]['filename']} was modified after being applied")


def status():
    files, applied = migration_files(), applied_migrations()
    check_integrity(files, applied)
    for f in files:
        print(f"{'applied' if f['version'] in applied else 'pending':8s} {f['filename']}")


def apply():
    files, applied = migration_files(), applied_migrations()
    check_integrity(files, applied)
    pending = [f for f in files if f["version"] not in applied]
    if not pending:
        print("no pending migrations")
        return
    for f in pending:
        print(f"applying {f['filename']} ...", flush=True)
        # Values interpolated with psql :'var' quoting; they come from validated filenames/hashes.
        psql(
            f"\\set version '{f['version']}'\n"
            f"\\set filename '{f['filename']}'\n"
            f"\\set checksum '{f['checksum']}'\n"
            "BEGIN;\n"
            "SET LOCAL lock_timeout = '30s';\n"
            f"{f['content']}\n"
            "INSERT INTO app.schema_migrations (version, filename, checksum)"
            " VALUES (:'version', :'filename', :'checksum');\n"
            "COMMIT;\n"
        )
        print(f"applied  {f['filename']}")


def scram_sha256_verifier(password, iterations=4096):
    """Build a PostgreSQL SCRAM-SHA-256 verifier so the plaintext never reaches the server."""
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"


def _set_role_password(role, env_var):
    load_dotenv()
    password = os.getenv(env_var, "")
    if len(password) < 16:
        fail(f"{env_var} must be set in .env and be at least 16 characters")
    if not password.isascii() or not password.isprintable():
        fail(f"{env_var} must contain printable ASCII characters only")

    exists = psql(f"SELECT count(*) FROM pg_roles WHERE rolname = '{role}';").strip()
    if exists != "1":
        fail(f"role {role} does not exist; run `apply` first")

    verifier = scram_sha256_verifier(password)
    psql(f"\\set verifier '{verifier}'\nALTER ROLE {role} PASSWORD :'verifier';\n")
    print(f"password set for {role}")


def set_app_role_password():
    _set_role_password(APP_ROLE, "DB_APP_RO_PASSWORD")


def set_auth_role_password():
    _set_role_password(AUTH_ROLE, "DB_AUTH_PASSWORD")


COMMANDS = {
    "status": status,
    "apply": apply,
    "set-app-role-password": set_app_role_password,
    "set-auth-role-password": set_auth_role_password,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"usage: python {sys.argv[0]} {{{'|'.join(COMMANDS)}}}")
    COMMANDS[sys.argv[1]]()
