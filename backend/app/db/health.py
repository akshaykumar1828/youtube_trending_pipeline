"""Readiness check: connectivity, read access to the application views, read-only session."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

_READINESS = text("""
    SELECT current_user                                     AS role,
           current_setting('transaction_read_only')         AS read_only,
           EXISTS (SELECT 1 FROM app.trending_snapshots)    AS snapshots_readable,
           EXISTS (SELECT 1 FROM app.video_details)         AS video_details_readable
""")


def check_database(conn: Connection) -> dict:
    """Raises on connection or permission failure; otherwise reports what it verified."""
    row = conn.execute(_READINESS).one()
    read_only = row.read_only == "on"
    ok = read_only and row.snapshots_readable and row.video_details_readable
    return {
        "status": "ok" if ok else "failed",
        "role": row.role,
        "read_only": read_only,
        "views_readable": bool(row.snapshots_readable and row.video_details_readable),
    }
