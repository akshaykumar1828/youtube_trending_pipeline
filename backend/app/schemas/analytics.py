"""Analytics response models (field names and semantics mirror app/repositories/analytics.py)."""

from pydantic import BaseModel, Field

ENGAGEMENT = "(SUM(likes) + SUM(comments)) / SUM(views); null when views sum to 0."


class CategoryPerformance(BaseModel):
    category: str
    trending_volume: int = Field(description="SNAPSHOT-LEVEL: filtered snapshots whose own category is this one.")
    volume_share_pct: float | None = Field(description="SNAPSHOT-LEVEL: trending_volume / all filtered snapshots * 100.")
    unique_videos: int = Field(description="VIDEO-LEVEL: videos whose latest snapshot within the filtered dataset "
                                           "is in this category (sums to the overall unique video count).")
    views: int = Field(description="VIDEO-LEVEL: sum of those latest snapshots' view_count (once per video).")
    engagement_rate: float | None = Field(description="VIDEO-LEVEL: " + ENGAGEMENT)


class CountryPerformance(BaseModel):
    country_code: str
    country_name: str | None
    trending_volume: int = Field(description="SNAPSHOT-LEVEL: filtered snapshots in this country.")
    unique_videos: int = Field(description="COUNTRY-LEVEL: videos that trended in this country within the filters. "
                                           "A video trending in several countries counts in each.")
    views_of_trending_videos: int = Field(
        description="COUNTRY-LEVEL: sum of the GLOBAL lifetime view_count of each video's latest filtered "
                    "snapshot in this country. These are NOT views from this country and are NOT additive "
                    "across countries.")
    engagement_rate: float | None = Field(description="COUNTRY-LEVEL: " + ENGAGEMENT)


class EngagementTotals(BaseModel):
    videos: int
    videos_without_views: int = Field(description="Videos excluded from per-video rates because views are 0.")
    views: int
    likes: int
    comments: int
    engagement_rate: float | None = Field(description="Aggregate rate; equals the overview KPI for the same filters.")


class EngagementDistribution(BaseModel):
    """Percentiles (linear interpolation) of per-video engagement rate, videos with views > 0."""

    p25: float | None
    p50: float | None
    p75: float | None
    p90: float | None


class HistogramBucket(BaseModel):
    lower_pct: float
    upper_pct: float | None = Field(description="Exclusive upper bound in percent; null for the open '>= 10%' bucket.")
    videos: int


class CategoryEngagement(BaseModel):
    category: str
    videos: int
    videos_with_views: int
    p25: float | None
    p50: float | None
    p75: float | None


class ScatterPoint(BaseModel):
    video_id: str
    title: str | None
    category: str
    views: int | None
    engagement_rate: float | None


class EngagementAnalysis(BaseModel):
    """VIDEO-LEVEL engagement over each video's latest snapshot within the filtered dataset.
    Hidden like counts are stored as 0 and counted as 0."""

    totals: EngagementTotals
    distribution: EngagementDistribution
    histogram: list[HistogramBucket] = Field(description="1-point buckets 0-10% plus '>= 10%'; all buckets returned.")
    by_category: list[CategoryEngagement]
    scatter: list[ScatterPoint] = Field(description="Top videos by views (ties: video_id).")


class ChannelPerformance(BaseModel):
    channel_id: str
    channel_title: str | None = Field(description="From the channel's most recent filtered snapshot.")
    subscribers: int | None = Field(description="From the channel's most recent filtered snapshot.")
    unique_videos: int = Field(description="VIDEO-LEVEL: videos whose latest filtered snapshot belongs to the channel.")
    trending_volume: int = Field(description="SNAPSHOT-LEVEL: filtered snapshots of the channel's videos.")
    views: int = Field(description="VIDEO-LEVEL: sum of those latest snapshots' view_count.")
    engagement_rate: float | None = Field(description="VIDEO-LEVEL: " + ENGAGEMENT)
