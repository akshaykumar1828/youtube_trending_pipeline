"""Overview page queries: KPIs with period-over-period change, daily trending volume.

Reads app.trending_snapshots only. "Latest snapshot" = latest WITHIN THE
FILTERED DATASET (see common.py), not the global latest in app.video_details.
"""

from dataclasses import replace
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

from . import meta
from .common import (
    ENGAGEMENT_RATE,
    LATEST_PER_VIDEO,
    check_choice,
    filtered_cte,
    pct_change,
    pts_change,
    to_float,
    to_int,
)
from .filters import Filters

_KPI_COLUMNS = "video_id, channel_id, trending_date, country_code, view_count, like_count, comment_count"

COUNT_METRICS = ("unique_videos", "trending_volume", "views", "unique_channels")

# split_by value -> fixed column name
DAILY_SPLITS = {None: None, "country": "country_code", "category": "category"}


def _period_metrics(conn, filters):
    """KPI values for one period.

    trending_volume  snapshot-level  count(*) of filtered snapshots
    unique_channels  snapshot-level  distinct non-NULL channel_id among filtered snapshots
    unique_videos    video-level     number of videos (one latest filtered snapshot each)
    views            video-level     SUM(view_count) over latest filtered snapshots
    engagement_rate  video-level     (SUM(likes) + SUM(comments)) / SUM(views) over the same
                                     snapshots; None when views sum to 0
    """
    filtered, params = filtered_cte(filters, _KPI_COLUMNS)
    sql = f"""
        WITH {filtered},
        {LATEST_PER_VIDEO}
        SELECT
            (SELECT count(*) FROM filtered)                                AS trending_volume,
            (SELECT count(*) FROM (SELECT channel_id FROM filtered
                                   WHERE channel_id IS NOT NULL
                                   GROUP BY channel_id) c)                 AS unique_channels,
            count(*)                                                       AS unique_videos,
            COALESCE(sum(view_count), 0)                                   AS views,
            {ENGAGEMENT_RATE}                                              AS engagement_rate
        FROM latest
    """
    row = conn.execute(text(sql), params).one()
    return {
        "trending_volume": to_int(row.trending_volume),
        "unique_channels": to_int(row.unique_channels),
        "unique_videos": to_int(row.unique_videos),
        "views": to_int(row.views),
        "engagement_rate": to_float(row.engagement_rate),
    }


def get_kpis(conn: Connection, filters: Filters) -> dict:
    """Overview KPIs for the filtered period and the immediately preceding period
    of equal length (same countries/categories).

    The previous period is "available" only if it lies entirely within the data
    (starts on or after the database min date); otherwise previous values and
    changes are None. Counts and views change in percent; engagement_rate changes
    in percentage points. Change is None when the previous value is missing or 0.

    Note: views are lifetime counts of the videos trending in each period, so the
    views change compares two sets of videos, not views gained.
    """
    min_date, _ = meta.get_date_range(conn)
    prev_start, prev_end = filters.previous_period()
    available = prev_start >= min_date

    current = _period_metrics(conn, filters)
    previous = (
        _period_metrics(conn, replace(filters, start_date=prev_start, end_date=prev_end))
        if available else None
    )

    result = {
        "period": {"start_date": filters.start_date, "end_date": filters.end_date, "days": filters.days},
        "previous_period": {"start_date": prev_start, "end_date": prev_end, "days": filters.days,
                            "available": available},
    }
    for name in COUNT_METRICS:
        prev = previous[name] if previous else None
        result[name] = {"value": current[name], "previous": prev, "change_pct": pct_change(current[name], prev)}
    prev_rate = previous["engagement_rate"] if previous else None
    result["engagement_rate"] = {
        "value": current["engagement_rate"],
        "previous": prev_rate,
        "change_pts": pts_change(current["engagement_rate"], prev_rate),
    }
    return result


def get_daily_volume(conn: Connection, filters: Filters, split_by=None) -> dict:
    """Daily trending activity within the filters, every date in the range present (zero-filled).

    trending_volume  snapshot-level  snapshots on that date
    unique_videos    video-level     distinct videos on that date (a video trending in
                                     several selected countries that day counts once)
    No daily views: view counts are cumulative, so a daily sum is not meaningful.

    split_by: None, "country" or "category" (snapshot's own category). Split series
    contain the keys present in the filtered data, each zero-filled over the range.
    """
    column = check_choice("split_by", split_by, DAILY_SPLITS)
    filtered, params = filtered_cte(filters, "video_id, trending_date, country_code, category")
    dates = [filters.start_date + timedelta(days=i) for i in range(filters.days)]

    if column is None:
        sql = f"""
            WITH {filtered},
            per_video AS (
                SELECT trending_date, video_id, count(*) AS n
                FROM filtered GROUP BY trending_date, video_id
            ),
            daily AS (
                SELECT trending_date, sum(n) AS trending_volume, count(*) AS unique_videos
                FROM per_video GROUP BY trending_date
            )
            SELECT CAST(d AS date) AS day,
                   COALESCE(daily.trending_volume, 0) AS trending_volume,
                   COALESCE(daily.unique_videos, 0)   AS unique_videos
            FROM generate_series(CAST(:start_date AS date), CAST(:end_date AS date), interval '1 day') AS d
            LEFT JOIN daily ON daily.trending_date = CAST(d AS date)
            ORDER BY day
        """
        points = [
            {"date": r.day, "trending_volume": to_int(r.trending_volume), "unique_videos": to_int(r.unique_videos)}
            for r in conn.execute(text(sql), params)
        ]
        return {"split_by": None, "series": [{"key": None, "points": points}]}

    sql = f"""
        WITH {filtered},
        per_video AS (
            SELECT trending_date, {column} AS key, video_id, count(*) AS n
            FROM filtered GROUP BY trending_date, {column}, video_id
        )
        SELECT trending_date, key, sum(n) AS trending_volume, count(*) AS unique_videos
        FROM per_video GROUP BY trending_date, key
    """
    by_key = {}
    for r in conn.execute(text(sql), params):
        by_key.setdefault(r.key, {})[r.trending_date] = (to_int(r.trending_volume), to_int(r.unique_videos))

    series = []
    for key in sorted(by_key):
        days = by_key[key]
        series.append({
            "key": key,
            "points": [
                {"date": d, "trending_volume": days.get(d, (0, 0))[0], "unique_videos": days.get(d, (0, 0))[1]}
                for d in dates
            ],
        })
    return {"split_by": split_by, "series": series}
