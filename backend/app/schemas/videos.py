"""Video response models (field names and semantics mirror app/repositories/videos.py)."""

import datetime as dt

from pydantic import BaseModel, Field


class VideoListItem(BaseModel):
    """One video. Title, channel, category, counts and engagement come from its latest snapshot
    WITHIN THE FILTERED DATASET; the date/country fields aggregate its filtered snapshots."""

    video_id: str
    title: str | None
    channel_id: str | None
    channel_title: str | None
    category: str
    thumbnail_url: str | None
    published_at: dt.datetime | None
    duration_sec: int | None
    views: int | None = Field(description="Global lifetime view_count at the latest filtered snapshot.")
    likes: int | None
    comments: int | None
    engagement_rate: float | None = Field(description="(likes + comments) / views; null when views are 0.")
    trending_countries: list[str] = Field(description="Countries with a filtered snapshot.")
    days_on_trending: int = Field(description="Distinct trending dates within the filters.")
    first_trending_date: dt.date
    last_trending_date: dt.date
    snapshot_count: int = Field(description="Filtered snapshots (country x day appearances).")


class VideoPage(BaseModel):
    items: list[VideoListItem]
    page: int
    page_size: int
    total: int = Field(description="Videos matching the filters and search.")
    total_pages: int


class ChannelInfo(BaseModel):
    channel_id: str | None
    title: str | None
    description: str | None
    custom_url: str | None
    country: str | None
    published_at: dt.datetime | None
    subscribers: int | None
    hidden_subscribers: bool | None
    total_views: int | None
    video_count: int | None


class VideoDetail(BaseModel):
    """From app.video_details: the video's GLOBALLY latest snapshot (latest date, then highest
    views, then country code) plus its full lifecycle summary. Not affected by filters."""

    video_id: str
    title: str | None
    description: str | None
    tags: str | None
    category: str
    published_at: dt.datetime | None
    duration_sec: int | None
    definition: str | None
    dimension: str | None
    licensed_content: bool | None
    thumbnail_url: str | None
    views: int | None
    likes: int | None
    comments: int | None
    engagement_rate: float | None
    latest_country_code: str
    latest_trending_date: dt.date
    first_trending_date: dt.date
    last_trending_date: dt.date
    trending_countries: list[str]
    snapshot_count: int
    channel: ChannelInfo


class HistoryPoint(BaseModel):
    """One trending snapshot (country x day). Views are the global lifetime count at that snapshot;
    do not sum them across snapshots."""

    country_code: str
    country_name: str | None
    trending_date: dt.date
    views: int | None
    likes: int | None
    comments: int | None
    engagement_rate: float | None
