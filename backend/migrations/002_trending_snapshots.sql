-- 002: app.trending_snapshots
--
-- One row per (country, video, trending date): the complete country-specific
-- trending history, with only the narrow columns the application needs.
-- Long text (descriptions, tags) lives in app.video_details. `will_trend` is
-- intentionally excluded.
--
-- Built directly from the 9 raw tables (not from the hand-made
-- public.youtube_trending_all view) so the application depends only on the
-- raw source tables. The raw tables are only read.
--
-- Metric definitions the application uses on top of this view:
--   unique videos   = COUNT(DISTINCT video_id)
--   trending volume = COUNT(*) of snapshot rows
--   views           = view_count of each video's latest snapshot, counted once
--   engagement rate = (SUM(like_count) + SUM(comment_count)) / SUM(view_count)
--                     over those same latest snapshots
--   latest snapshot = ORDER BY trending_date DESC, view_count DESC, country_code ASC
--                     (same rule as app.video_details, applied within the filters)

CREATE MATERIALIZED VIEW app.trending_snapshots AS
WITH raw AS (
    SELECT 'AU'::text AS country_code, t.* FROM public.youtube_trending_au t
    UNION ALL
    SELECT 'CA'::text, t.* FROM public.youtube_trending_ca t
    UNION ALL
    SELECT 'GB'::text, t.* FROM public.youtube_trending_gb t
    UNION ALL
    SELECT 'IE'::text, t.* FROM public.youtube_trending_ie t
    UNION ALL
    SELECT 'IN'::text, t.* FROM public.youtube_trending_in t
    UNION ALL
    SELECT 'NZ'::text, t.* FROM public.youtube_trending_nz t
    UNION ALL
    SELECT 'SG'::text, t.* FROM public.youtube_trending_sg t
    UNION ALL
    SELECT 'US'::text, t.* FROM public.youtube_trending_us t
    UNION ALL
    SELECT 'ZA'::text, t.* FROM public.youtube_trending_za t
)
SELECT
    country_code,
    video_trending_country                                  AS country_name,
    video_id,
    video_trending_date                                     AS trending_date,
    video_published_at                                      AS published_at,
    channel_id,
    channel_title,
    video_title,
    COALESCE(NULLIF(btrim(video_category_id), ''), 'Unknown') AS category,
    EXTRACT(EPOCH FROM video_duration::interval)::integer   AS duration_sec,
    video_view_count                                        AS view_count,
    video_like_count                                        AS like_count,
    video_comment_count                                     AS comment_count,
    channel_subscriber_count,
    channel_view_count,
    channel_video_count,
    video_default_thumbnail                                 AS thumbnail_url
FROM raw
WITH DATA;

-- Natural key (verified: no duplicate (video, date) within a country).
-- Also required for REFRESH MATERIALIZED VIEW CONCURRENTLY.
CREATE UNIQUE INDEX trending_snapshots_key
    ON app.trending_snapshots (country_code, video_id, trending_date);

-- Date-range + country filters (KPIs, time series, category/region analytics).
CREATE INDEX trending_snapshots_date_country
    ON app.trending_snapshots (trending_date, country_code);

-- Per-video history and "latest snapshot per video" lookups.
CREATE INDEX trending_snapshots_video_latest
    ON app.trending_snapshots (video_id, trending_date DESC);

COMMENT ON MATERIALIZED VIEW app.trending_snapshots IS
    'Country-specific trending history, one row per (country_code, video_id, trending_date). Refresh after ingestion.';

ANALYZE app.trending_snapshots;
