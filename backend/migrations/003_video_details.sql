-- 003: app.video_details
--
-- One row per video_id: the video's metadata and long text taken from its
-- single LATEST snapshot across all countries, plus a lifecycle summary.
-- Country-specific history is NOT discarded: it remains in app.trending_snapshots.
--
-- "Latest snapshot" selection (deterministic):
--   1. the most recent video_trending_date across all countries;
--   2. if the video trended in several countries on that date, the snapshot
--      with the highest view count (views only grow between fetches, so this
--      is the most recently fetched one);
--   3. if still tied, the alphabetically first country_code.
-- Verified before writing: 20,061 videos have their latest date in more than
-- one country; 1,366 of those differ in view count; none differ in title.
--
-- `will_trend` is intentionally excluded.

CREATE MATERIALIZED VIEW app.video_details AS
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
),
ranked AS (
    SELECT
        raw.*,
        row_number() OVER (
            PARTITION BY video_id
            ORDER BY video_trending_date DESC, video_view_count DESC NULLS LAST, country_code ASC
        ) AS snapshot_rank
    FROM raw
),
lifecycle AS (
    SELECT
        video_id,
        min(video_trending_date)                            AS first_trending_date,
        max(video_trending_date)                            AS last_trending_date,
        array_agg(DISTINCT country_code ORDER BY country_code) AS trending_countries,
        count(*)                                            AS snapshot_count
    FROM raw
    GROUP BY video_id
)
SELECT
    r.video_id,
    r.country_code                                          AS latest_country_code,
    r.video_trending_date                                   AS latest_trending_date,
    r.video_published_at                                    AS published_at,
    r.video_title,
    r.video_description,
    r.video_tags,
    COALESCE(NULLIF(btrim(r.video_category_id), ''), 'Unknown') AS category,
    EXTRACT(EPOCH FROM r.video_duration::interval)::integer AS duration_sec,
    r.video_definition,
    r.video_dimension,
    r.video_licensed_content,
    r.video_default_thumbnail                               AS thumbnail_url,
    r.video_view_count                                      AS view_count,
    r.video_like_count                                      AS like_count,
    r.video_comment_count                                   AS comment_count,
    r.channel_id,
    r.channel_title,
    r.channel_description,
    r.channel_custom_url,
    r.channel_country,
    r.channel_published_at,
    r.channel_subscriber_count,
    r.channel_have_hidden_subscribers,
    r.channel_view_count,
    r.channel_video_count,
    l.first_trending_date,
    l.last_trending_date,
    l.trending_countries,
    l.snapshot_count
FROM ranked r
JOIN lifecycle l USING (video_id)
WHERE r.snapshot_rank = 1
WITH DATA;

-- One row per video; also required for REFRESH MATERIALIZED VIEW CONCURRENTLY.
CREATE UNIQUE INDEX video_details_key
    ON app.video_details (video_id);

COMMENT ON MATERIALIZED VIEW app.video_details IS
    'One row per video_id from its latest snapshot (latest date, then highest views, then country_code). Refresh after ingestion.';

ANALYZE app.video_details;
