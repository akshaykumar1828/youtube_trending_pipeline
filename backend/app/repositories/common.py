"""Shared SQL building blocks and helpers for the application repositories.

LATEST SNAPSHOT — IMPORTANT
---------------------------
In the repositories, "latest snapshot" means the latest snapshot WITHIN THE
FILTERED DATASET: among the app.trending_snapshots rows that match the active
Filters (date range, countries, categories). It is NOT the globally latest
snapshot stored in app.video_details. Only when no filters narrow the data
(full date range, all countries, all categories) do the two coincide.

The selection rule is the same deterministic rule as app.video_details:
  1. most recent trending_date
  2. then highest view_count (NULLs last)
  3. then alphabetically first country_code
COLLATE "C" on the text sort keys only speeds up the sort: video IDs and
country codes are ASCII, so grouping and ordering results are unchanged.

HOW IT IS COMPUTED (performance; identical results)
---------------------------------------------------
Sorting every filtered snapshot (up to 1,135,886 rows) spills to disk under the
server's 4 MB work_mem. Instead, rule 1 is applied with a hash aggregate
(max(trending_date) per video, no sort), the filtered rows on that date are
joined back (the latest date plus any same-day ties in other countries), and
rules 2-3 run as a DISTINCT ON over only those candidates. Because every
candidate already has the maximum date, this selects exactly the row that the
full ORDER BY trending_date DESC, view_count DESC NULLS LAST, country_code
would select.

`filtered` is declared NOT MATERIALIZED so each reference is planned as its
own (index) scan instead of a temp-file copy of the filtered rows.

METRIC LEVELS
-------------
  snapshot-level : one row per (country, video, day) appearance, e.g. trending volume
  video-level    : each video counted once via its latest filtered snapshot,
                   e.g. unique videos, views, engagement rate
  country-level  : one row per (country, video) via the latest filtered snapshot
                   in that country. view_count is YouTube's GLOBAL count, so
                   country "views" are the global views of videos that trended
                   there, not views from that country, and are not additive
                   across countries.

SQL SAFETY
----------
Only two kinds of text are ever formatted into SQL: the fixed condition string
from Filters.sql_conditions() and identifiers taken from fixed whitelists in
repository code. Every value is a bound parameter.
"""

SNAPSHOTS = "app.trending_snapshots"
VIDEO_DETAILS = "app.video_details"

# Latest snapshot per video within `filtered` (rule 1 by hash aggregate, rules 2-3 on the candidates).
LATEST_PER_VIDEO = """latest_date AS (
    SELECT video_id, max(trending_date) AS trending_date
    FROM filtered GROUP BY video_id
),
latest AS (
    SELECT DISTINCT ON (f.video_id COLLATE "C") f.*
    FROM filtered f
    JOIN latest_date d ON d.video_id = f.video_id AND d.trending_date = f.trending_date
    ORDER BY f.video_id COLLATE "C", f.view_count DESC NULLS LAST, f.country_code COLLATE "C"
)"""

# Latest snapshot per (country, video) within `filtered`. (country_code, video_id, trending_date)
# is unique in app.trending_snapshots (unique index trending_snapshots_key), so the row at the
# max date is the only candidate and no further tie-break is needed.
LATEST_PER_COUNTRY_VIDEO = """country_latest_date AS (
    SELECT country_code, video_id, max(trending_date) AS trending_date
    FROM filtered GROUP BY country_code, video_id
),
country_latest AS (
    SELECT f.*
    FROM filtered f
    JOIN country_latest_date d
      ON d.country_code = f.country_code AND d.video_id = f.video_id AND d.trending_date = f.trending_date
)"""

# Aggregate engagement rate: (likes + comments) / views; NULL when there are no views.
ENGAGEMENT_RATE = (
    "(COALESCE(sum(like_count), 0) + COALESCE(sum(comment_count), 0))::float8"
    " / NULLIF(sum(view_count), 0)::float8"
)

# Per-row (per-video / per-snapshot) engagement rate; NULL when views are 0 or NULL.
ROW_ENGAGEMENT_RATE = (
    "CASE WHEN view_count > 0"
    " THEN (COALESCE(like_count, 0) + COALESCE(comment_count, 0))::float8 / view_count END"
)


class QueryParameterError(ValueError):
    """Invalid non-filter query parameter (sort, page, search, limit, id)."""

    def __init__(self, field, message):
        self.field = field
        super().__init__(f"{field}: {message}")


def filtered_cte(filters, columns):
    """`filtered AS (...)` over app.trending_snapshots plus its bound parameters.

    `columns` is a fixed column list from repository code, never user input.
    """
    conditions, params = filters.sql_conditions()
    return f"filtered AS NOT MATERIALIZED (SELECT {columns} FROM {SNAPSHOTS} WHERE {conditions})", params


def check_choice(field, value, choices):
    if value not in choices:
        raise QueryParameterError(field, f"must be one of {', '.join(str(c) for c in choices)}")
    return choices[value] if isinstance(choices, dict) else value


def check_int(field, value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise QueryParameterError(field, f"must be an integer between {low} and {high}")
    return value


def to_int(value):
    return None if value is None else int(value)


def to_float(value):
    return None if value is None else float(value)


def pct_change(current, previous):
    """Percent change; None when there is no previous value or it is 0."""
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / previous * 100


def pts_change(current, previous):
    """Change of a rate in percentage points; None when either rate is missing."""
    if current is None or previous is None:
        return None
    return (current - previous) * 100
