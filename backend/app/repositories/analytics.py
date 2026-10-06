"""Analytics queries: category, country, engagement, top channels.

Reads app.trending_snapshots only. "Latest snapshot" = latest WITHIN THE
FILTERED DATASET (see common.py), not the global latest in app.video_details.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .common import (
    ENGAGEMENT_RATE,
    LATEST_PER_COUNTRY_VIDEO,
    LATEST_PER_VIDEO,
    ROW_ENGAGEMENT_RATE,
    SNAPSHOTS,
    check_choice,
    check_int,
    filtered_cte,
    to_float,
    to_int,
)
from .filters import Filters

MAX_SCATTER = 500
MAX_CHANNELS = 50

# Engagement histogram: 1-percentage-point buckets over [0%, 10%) plus ">= 10%".
HISTOGRAM_UPPER = 0.10
HISTOGRAM_BUCKETS = 10
PERCENTILES = (0.25, 0.5, 0.75, 0.9)
CATEGORY_PERCENTILES = (0.25, 0.5, 0.75)

# sort key -> fixed column name
CHANNEL_SORTS = {"unique_videos": "unique_videos", "trending_volume": "trending_volume", "views": "views"}

# Narrowest columns each query needs (wide/text columns are fetched only where required).
_VIDEO_METRIC_COLUMNS = "video_id, trending_date, country_code, category, view_count, like_count, comment_count"
_COUNTRY_METRIC_COLUMNS = "video_id, trending_date, country_code, country_name, view_count, like_count, comment_count"


def get_category_performance(conn: Connection, filters: Filters) -> list[dict]:
    """One row per category, ordered by trending volume.

    trending_volume   snapshot-level  filtered snapshots in the category (snapshot's own category)
    volume_share_pct  snapshot-level  trending_volume / all filtered snapshots * 100
    unique_videos     video-level     videos whose latest filtered snapshot is in the category
                                      (sums to the overall unique video count)
    views             video-level     SUM(view_count) of those latest snapshots
    engagement_rate   video-level     (SUM(likes) + SUM(comments)) / SUM(views) of the same; None if 0 views
    """
    filtered, params = filtered_cte(filters, _VIDEO_METRIC_COLUMNS)
    sql = f"""
        WITH {filtered},
        {LATEST_PER_VIDEO},
        snap AS (SELECT category, count(*) AS trending_volume FROM filtered GROUP BY category),
        vid AS (
            SELECT category, count(*) AS unique_videos, COALESCE(sum(view_count), 0) AS views,
                   {ENGAGEMENT_RATE} AS engagement_rate
            FROM latest GROUP BY category
        )
        SELECT * FROM (
            SELECT COALESCE(snap.category, vid.category)      AS category,
                   COALESCE(snap.trending_volume, 0)           AS trending_volume,
                   -- total volume = sum over the (few) category rows; avoids another scan
                   COALESCE(snap.trending_volume, 0)::float8 * 100
                       / NULLIF(sum(COALESCE(snap.trending_volume, 0)) OVER (), 0)::float8 AS volume_share_pct,
                   COALESCE(vid.unique_videos, 0)              AS unique_videos,
                   COALESCE(vid.views, 0)                      AS views,
                   vid.engagement_rate
            FROM snap FULL JOIN vid ON vid.category = snap.category
        ) per_category
        ORDER BY trending_volume DESC, category COLLATE "C"
    """
    return [
        {
            "category": r.category,
            "trending_volume": to_int(r.trending_volume),
            "volume_share_pct": to_float(r.volume_share_pct),
            "unique_videos": to_int(r.unique_videos),
            "views": to_int(r.views),
            "engagement_rate": to_float(r.engagement_rate),
        }
        for r in conn.execute(text(sql), params)
    ]


def get_country_performance(conn: Connection, filters: Filters) -> list[dict]:
    """One row per country, ordered by trending volume (country-level metrics).

    trending_volume           snapshot-level  filtered snapshots in the country
    unique_videos             country-level   videos that trended in the country within the filters
                                              (a multi-country video counts in each country)
    views_of_trending_videos  country-level   SUM of the GLOBAL view_count of each video's latest
                                              filtered snapshot in that country. Not views from the
                                              country, and not additive across countries.
    engagement_rate           country-level   (SUM(likes) + SUM(comments)) / SUM(views) of the same
    """
    filtered, params = filtered_cte(filters, _COUNTRY_METRIC_COLUMNS)
    sql = f"""
        WITH {filtered},
        {LATEST_PER_COUNTRY_VIDEO},
        snap AS (
            SELECT country_code, min(country_name) AS country_name, count(*) AS trending_volume
            FROM filtered GROUP BY country_code
        ),
        vid AS (
            SELECT country_code, count(*) AS unique_videos,
                   COALESCE(sum(view_count), 0) AS views_of_trending_videos,
                   {ENGAGEMENT_RATE} AS engagement_rate
            FROM country_latest GROUP BY country_code
        )
        SELECT snap.country_code, snap.country_name, snap.trending_volume,
               vid.unique_videos, vid.views_of_trending_videos, vid.engagement_rate
        FROM snap JOIN vid ON vid.country_code = snap.country_code
        ORDER BY snap.trending_volume DESC, snap.country_code COLLATE "C"
    """
    return [
        {
            "country_code": r.country_code,
            "country_name": r.country_name,
            "trending_volume": to_int(r.trending_volume),
            "unique_videos": to_int(r.unique_videos),
            "views_of_trending_videos": to_int(r.views_of_trending_videos),
            "engagement_rate": to_float(r.engagement_rate),
        }
        for r in conn.execute(text(sql), params)
    ]


def get_engagement_analysis(conn: Connection, filters: Filters, scatter_limit: int = 200) -> dict:
    """Video-level engagement over each video's latest filtered snapshot.

    totals       views / likes / comments sums and the aggregate engagement rate
                 (equal to the overview KPI values for the same filters)
    distribution per-video engagement rate = (likes + comments) / views, only for videos
                 with views > 0 (videos_without_views reports how many were excluded).
                 Percentiles use percentile_cont (linear interpolation). Hidden like
                 counts are stored as 0 and counted as 0.
    histogram    1-point buckets [0%,1%) ... [9%,10%) plus [10%, open); all buckets returned
    by_category  per category (latest filtered snapshot's category): video count, videos
                 with views, and 25/50/75th percentile of per-video engagement rate
    scatter      top `scatter_limit` videos by views (ties: video_id), deterministic
    """
    limit = check_int("scatter_limit", scatter_limit, 1, MAX_SCATTER)
    filtered, params = filtered_cte(filters, _VIDEO_METRIC_COLUMNS)
    params = {**params, "scatter_limit": limit,
              "percentiles": list(PERCENTILES), "category_percentiles": list(CATEGORY_PERCENTILES)}
    sql = f"""
        WITH {filtered},
        {LATEST_PER_VIDEO},
        rated AS (
            SELECT video_id, trending_date, country_code, category, view_count, like_count, comment_count,
                   {ROW_ENGAGEMENT_RATE} AS engagement_rate
            FROM latest
        )
        SELECT
            count(*)                                            AS videos,
            count(*) FILTER (WHERE engagement_rate IS NULL)     AS videos_without_views,
            COALESCE(sum(view_count), 0)                        AS views,
            COALESCE(sum(like_count), 0)                        AS likes,
            COALESCE(sum(comment_count), 0)                     AS comments,
            {ENGAGEMENT_RATE}                                   AS engagement_rate,
            percentile_cont(CAST(:percentiles AS float8[]))
                WITHIN GROUP (ORDER BY engagement_rate)         AS percentiles,
            (SELECT json_agg(json_build_object('bucket', b, 'videos', n) ORDER BY b)
             FROM (SELECT width_bucket(engagement_rate, 0, {HISTOGRAM_UPPER}, {HISTOGRAM_BUCKETS}) AS b,
                          count(*) AS n
                   FROM rated WHERE engagement_rate IS NOT NULL GROUP BY 1) h) AS histogram,
            (SELECT json_agg(json_build_object(
                        'category', category, 'videos', videos, 'videos_with_views', with_views,
                        'percentiles', pct) ORDER BY category COLLATE "C")
             FROM (SELECT category, count(*) AS videos,
                          count(engagement_rate) AS with_views,
                          percentile_cont(CAST(:category_percentiles AS float8[]))
                              WITHIN GROUP (ORDER BY engagement_rate) AS pct
                   FROM rated GROUP BY category) c)              AS by_category,
            -- titles fetched only for the scatter rows, via the snapshot's unique key
            (SELECT json_agg(json_build_object(
                        'video_id', top.video_id, 'title', s.video_title, 'category', top.category,
                        'views', top.view_count, 'engagement_rate', top.engagement_rate)
                        ORDER BY top.view_count DESC NULLS LAST, top.video_id COLLATE "C")
             FROM (SELECT * FROM rated
                   ORDER BY view_count DESC NULLS LAST, video_id COLLATE "C"
                   LIMIT :scatter_limit) top
             JOIN {SNAPSHOTS} s
               ON s.country_code = top.country_code AND s.video_id = top.video_id
              AND s.trending_date = top.trending_date)            AS scatter
        FROM rated
    """
    r = conn.execute(text(sql), params).one()

    counts = {item["bucket"]: item["videos"] for item in (r.histogram or [])}
    histogram = []
    for bucket in range(1, HISTOGRAM_BUCKETS + 2):
        lower = (bucket - 1) * HISTOGRAM_UPPER / HISTOGRAM_BUCKETS * 100
        upper = None if bucket > HISTOGRAM_BUCKETS else bucket * HISTOGRAM_UPPER / HISTOGRAM_BUCKETS * 100
        histogram.append({"lower_pct": round(lower, 6), "upper_pct": None if upper is None else round(upper, 6),
                          "videos": counts.get(bucket, 0)})

    percentiles = r.percentiles or [None] * len(PERCENTILES)
    return {
        "totals": {
            "videos": to_int(r.videos),
            "videos_without_views": to_int(r.videos_without_views),
            "views": to_int(r.views),
            "likes": to_int(r.likes),
            "comments": to_int(r.comments),
            "engagement_rate": to_float(r.engagement_rate),
        },
        "distribution": {f"p{round(p * 100)}": to_float(v) for p, v in zip(PERCENTILES, percentiles)},
        "histogram": histogram,
        "by_category": [
            {
                "category": c["category"],
                "videos": c["videos"],
                "videos_with_views": c["videos_with_views"],
                # A category whose videos all lack views has no percentiles (None), like the overall ones.
                **{f"p{round(p * 100)}": v for p, v in
                   zip(CATEGORY_PERCENTILES, c["percentiles"] or [None] * len(CATEGORY_PERCENTILES))},
            }
            for c in (r.by_category or [])
        ],
        "scatter": [
            {"video_id": s["video_id"], "title": s["title"], "category": s["category"],
             "views": s["views"], "engagement_rate": s["engagement_rate"]}
            for s in (r.scatter or [])
        ],
    }


def get_top_channels(conn: Connection, filters: Filters, sort: str = "unique_videos", limit: int = 10) -> list[dict]:
    """Top channels within the filters.

    unique_videos    video-level     videos whose latest filtered snapshot belongs to the channel
    trending_volume  snapshot-level  filtered snapshots of the channel's videos
    views            video-level     SUM(view_count) of those latest snapshots
    engagement_rate  video-level     (SUM(likes) + SUM(comments)) / SUM(views) of the same
    channel_title,   channel-level   from the channel's most recent filtered snapshot
    subscribers                      (same tie-break rule as the latest-snapshot selection)

    sort: unique_videos | trending_volume | views (descending); ties: views, then channel_id.
    """
    column = check_choice("sort", sort, CHANNEL_SORTS)
    limit = check_int("limit", limit, 1, MAX_CHANNELS)
    filtered, params = filtered_cte(
        filters,
        "video_id, channel_id, channel_title, channel_subscriber_count, trending_date, country_code, "
        "view_count, like_count, comment_count",
    )
    sql = f"""
        WITH {filtered},
        {LATEST_PER_VIDEO},
        vid AS (
            SELECT channel_id, count(*) AS unique_videos, COALESCE(sum(view_count), 0) AS views,
                   {ENGAGEMENT_RATE} AS engagement_rate
            FROM latest GROUP BY channel_id
        ),
        -- one hash aggregate: snapshot volume and the channel's most recent filtered date
        snap AS (
            SELECT channel_id, count(*) AS trending_volume, max(trending_date) AS latest_date
            FROM filtered GROUP BY channel_id
        ),
        -- channel's most recent filtered snapshot: candidates on its latest date, then the
        -- same tie-break as video selection (video_id added as a final deterministic tie-break)
        chan AS (
            SELECT DISTINCT ON (f.channel_id COLLATE "C") f.channel_id, f.channel_title, f.channel_subscriber_count
            FROM filtered f
            JOIN snap ON snap.channel_id = f.channel_id AND snap.latest_date = f.trending_date
            ORDER BY f.channel_id COLLATE "C", f.view_count DESC NULLS LAST, f.country_code COLLATE "C",
                     f.video_id COLLATE "C"
        ),
        ranked AS (
            SELECT snap.channel_id, chan.channel_title, chan.channel_subscriber_count AS subscribers,
                   COALESCE(vid.unique_videos, 0) AS unique_videos, snap.trending_volume,
                   COALESCE(vid.views, 0) AS views, vid.engagement_rate
            FROM snap
            JOIN chan ON chan.channel_id = snap.channel_id
            LEFT JOIN vid ON vid.channel_id = snap.channel_id
            WHERE snap.channel_id IS NOT NULL
        )
        SELECT * FROM ranked
        ORDER BY {column} DESC, views DESC, channel_id COLLATE "C"
        LIMIT :limit
    """
    return [
        {
            "channel_id": r.channel_id,
            "channel_title": r.channel_title,
            "subscribers": to_int(r.subscribers),
            "unique_videos": to_int(r.unique_videos),
            "trending_volume": to_int(r.trending_volume),
            "views": to_int(r.views),
            "engagement_rate": to_float(r.engagement_rate),
        }
        for r in conn.execute(text(sql), {**params, "limit": limit})
    ]
