"""Video list, video detail and video history.

list_videos reads app.trending_snapshots and describes each video by its latest
snapshot WITHIN THE FILTERED DATASET (see common.py). get_video reads
app.video_details (the GLOBAL latest snapshot). get_video_history returns the
full, unfiltered history from app.trending_snapshots.
"""

import math

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .common import (
    LATEST_PER_VIDEO,
    ROW_ENGAGEMENT_RATE,
    SNAPSHOTS,
    VIDEO_DETAILS,
    QueryParameterError,
    check_choice,
    check_int,
    filtered_cte,
    to_float,
    to_int,
)
from .filters import Filters

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
MAX_PAGE = 1_000_000
SEARCH_MIN, SEARCH_MAX = 2, 100
VIDEO_ID_MAX = 64
HISTORY_LIMIT = 1000  # safety cap; the largest history today is 214 snapshots

# sort key -> fixed SQL expression over `latest l` (and `video_dates k` for date aggregates)
VIDEO_SORTS = {
    "views": "l.view_count",
    "likes": "l.like_count",
    "comments": "l.comment_count",
    "engagement_rate": ROW_ENGAGEMENT_RATE,  # count columns exist only in `latest`
    "days_on_trending": "k.days_on_trending",
    "first_trending_date": "k.first_trending_date",
    "last_trending_date": "k.last_trending_date",
    "published_at": "l.published_at",
}
SORTS_NEEDING_DATES = {"days_on_trending", "first_trending_date", "last_trending_date"}
SORT_ORDERS = {"asc": "ASC", "desc": "DESC"}

# Narrow columns used to pick the latest row and the sort key for every video.
_KEY_COLUMNS = "video_id, trending_date, country_code, view_count, like_count, comment_count, published_at"
_SEARCH_COLUMNS = ", video_title, channel_title"


def _search_pattern(search):
    """Validated ILIKE pattern with LIKE wildcards escaped, or None for no search."""
    if search is None:
        return None
    if not isinstance(search, str):
        raise QueryParameterError("search", "must be a string")
    term = search.strip()
    if not term:
        return None
    if not SEARCH_MIN <= len(term) <= SEARCH_MAX:
        raise QueryParameterError("search", f"must be {SEARCH_MIN} to {SEARCH_MAX} characters")
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return term, f"%{escaped}%"


def list_videos(conn: Connection, filters: Filters, sort: str = "views", order: str = "desc",
                page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, search=None) -> dict:
    """Paginated list of videos trending within the filters (video-level, one row per video).

    From each video's latest FILTERED snapshot: title, channel, category, thumbnail,
    published_at, duration, views, likes, comments, engagement_rate (None if 0 views).
    From all of its filtered snapshots: trending_countries, days_on_trending (distinct
    dates), first/last_trending_date, snapshot_count.

    search: case-insensitive substring of the latest filtered title or channel title,
    or an exact video_id. LIKE wildcards are matched literally. Blank = no search.
    sort/order: fixed whitelists; NULLs last; ties broken by video_id for stable pages.

    Query strategy (results identical to sorting the full rows): only narrow key
    columns are used to pick each video's latest filtered snapshot and its sort key;
    the requested page of (video, latest snapshot) keys is taken first, then display
    columns and per-video aggregates are fetched for those page videos only.
    """
    sort_expr = check_choice("sort", sort, VIDEO_SORTS)
    direction = check_choice("order", order, SORT_ORDERS)
    page = check_int("page", page, 1, MAX_PAGE)
    page_size = check_int("page_size", page_size, 1, MAX_PAGE_SIZE)
    search_term = _search_pattern(search)

    conditions, _ = filters.sql_conditions()
    filtered, params = filtered_cte(filters, _KEY_COLUMNS + (_SEARCH_COLUMNS if search_term else ""))
    params = {**params, "limit": page_size, "offset": (page - 1) * page_size}

    where = ""
    if search_term:
        params["search_exact"], params["search_pattern"] = search_term
        where = (
            "WHERE l.video_title ILIKE :search_pattern ESCAPE '\\'"
            " OR l.channel_title ILIKE :search_pattern ESCAPE '\\'"
            " OR l.video_id = :search_exact"
        )

    dates_cte, dates_join = "", ""
    if sort in SORTS_NEEDING_DATES:
        dates_cte = """
        video_dates AS (
            -- COLLATE "C" only speeds up the grouping sort (ASCII ids; same groups)
            SELECT video_id COLLATE "C" AS video_id, count(DISTINCT trending_date) AS days_on_trending,
                   min(trending_date) AS first_trending_date, max(trending_date) AS last_trending_date
            FROM filtered GROUP BY video_id COLLATE "C"
        ),"""
        dates_join = "JOIN video_dates k ON k.video_id = l.video_id"

    keys_cte = f"""
        WITH {filtered},
        {LATEST_PER_VIDEO},{dates_cte}
        keyed AS (
            SELECT l.video_id, l.trending_date, l.country_code, {sort_expr} AS sort_value
            FROM latest l {dates_join}
            {where}
        )
    """
    page_sql = f"""{keys_cte},
        page AS (
            SELECT video_id, trending_date, country_code, sort_value, count(*) OVER () AS total
            FROM keyed
            ORDER BY sort_value {direction} NULLS LAST, video_id COLLATE "C" ASC
            LIMIT :limit OFFSET :offset
        ),
        page_aggregates AS (
            SELECT video_id,
                   array_agg(DISTINCT country_code ORDER BY country_code) AS trending_countries,
                   count(DISTINCT trending_date) AS days_on_trending,
                   min(trending_date) AS first_trending_date,
                   max(trending_date) AS last_trending_date,
                   count(*) AS snapshot_count
            FROM {SNAPSHOTS}
            WHERE {conditions} AND video_id IN (SELECT video_id FROM page)
            GROUP BY video_id
        )
        SELECT page.total, s.video_id, s.video_title, s.channel_id, s.channel_title, s.category,
               s.thumbnail_url, s.published_at, s.duration_sec, s.view_count, s.like_count, s.comment_count,
               {ROW_ENGAGEMENT_RATE} AS engagement_rate,  -- count columns exist only in `s`
               a.trending_countries, a.days_on_trending, a.first_trending_date, a.last_trending_date,
               a.snapshot_count
        FROM page
        JOIN {SNAPSHOTS} s
          ON s.country_code = page.country_code AND s.video_id = page.video_id
         AND s.trending_date = page.trending_date
        JOIN page_aggregates a ON a.video_id = page.video_id
        ORDER BY page.sort_value {direction} NULLS LAST, page.video_id COLLATE "C" ASC
    """
    result = conn.execute(text(page_sql), params).all()
    if result:
        total = result[0].total
    else:  # page past the end: the window count is unavailable, so count separately
        total = conn.execute(text(f"{keys_cte} SELECT count(*) FROM keyed"), params).scalar_one()

    items = [
        {
            "video_id": r.video_id,
            "title": r.video_title,
            "channel_id": r.channel_id,
            "channel_title": r.channel_title,
            "category": r.category,
            "thumbnail_url": r.thumbnail_url,
            "published_at": r.published_at,
            "duration_sec": to_int(r.duration_sec),
            "views": to_int(r.view_count),
            "likes": to_int(r.like_count),
            "comments": to_int(r.comment_count),
            "engagement_rate": to_float(r.engagement_rate),
            "trending_countries": list(r.trending_countries),
            "days_on_trending": to_int(r.days_on_trending),
            "first_trending_date": r.first_trending_date,
            "last_trending_date": r.last_trending_date,
            "snapshot_count": to_int(r.snapshot_count),
        }
        for r in result
    ]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": to_int(total),
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def _check_video_id(video_id):
    if not isinstance(video_id, str) or not 1 <= len(video_id) <= VIDEO_ID_MAX:
        raise QueryParameterError("video_id", f"must be a string of 1 to {VIDEO_ID_MAX} characters")
    return video_id


def get_video(conn: Connection, video_id: str):
    """Video detail from app.video_details (its GLOBAL latest snapshot + lifecycle summary).

    Returns None if the video does not exist.
    """
    sql = f"""
        SELECT *, {ROW_ENGAGEMENT_RATE} AS engagement_rate
        FROM {VIDEO_DETAILS} WHERE video_id = :video_id
    """
    r = conn.execute(text(sql), {"video_id": _check_video_id(video_id)}).mappings().one_or_none()
    if r is None:
        return None
    return {
        "video_id": r["video_id"],
        "title": r["video_title"],
        "description": r["video_description"],
        "tags": r["video_tags"],
        "category": r["category"],
        "published_at": r["published_at"],
        "duration_sec": to_int(r["duration_sec"]),
        "definition": r["video_definition"],
        "dimension": r["video_dimension"],
        "licensed_content": r["video_licensed_content"],
        "thumbnail_url": r["thumbnail_url"],
        "views": to_int(r["view_count"]),
        "likes": to_int(r["like_count"]),
        "comments": to_int(r["comment_count"]),
        "engagement_rate": to_float(r["engagement_rate"]),
        "latest_country_code": r["latest_country_code"],
        "latest_trending_date": r["latest_trending_date"],
        "first_trending_date": r["first_trending_date"],
        "last_trending_date": r["last_trending_date"],
        "trending_countries": list(r["trending_countries"]),
        "snapshot_count": to_int(r["snapshot_count"]),
        "channel": {
            "channel_id": r["channel_id"],
            "title": r["channel_title"],
            "description": r["channel_description"],
            "custom_url": r["channel_custom_url"],
            "country": r["channel_country"],
            "published_at": r["channel_published_at"],
            "subscribers": to_int(r["channel_subscriber_count"]),
            "hidden_subscribers": r["channel_have_hidden_subscribers"],
            "total_views": to_int(r["channel_view_count"]),
            "video_count": to_int(r["channel_video_count"]),
        },
    }


def get_video_history(conn: Connection, video_id: str) -> list[dict]:
    """Every trending snapshot of the video (all countries, all dates; NOT filtered),
    ordered by trending_date then country_code. Empty list if the video does not exist.
    """
    sql = f"""
        SELECT country_code, country_name, trending_date, view_count, like_count, comment_count,
               {ROW_ENGAGEMENT_RATE} AS engagement_rate
        FROM {SNAPSHOTS}
        WHERE video_id = :video_id
        ORDER BY trending_date, country_code COLLATE "C"
        LIMIT :limit
    """
    return [
        {
            "country_code": r.country_code,
            "country_name": r.country_name,
            "trending_date": r.trending_date,
            "views": to_int(r.view_count),
            "likes": to_int(r.like_count),
            "comments": to_int(r.comment_count),
            "engagement_rate": to_float(r.engagement_rate),
        }
        for r in conn.execute(text(sql), {"video_id": _check_video_id(video_id), "limit": HISTORY_LIMIT})
    ]
