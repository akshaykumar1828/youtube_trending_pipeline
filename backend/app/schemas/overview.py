"""Overview response models (field names and semantics mirror app/repositories/overview.py)."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

PCT_CHANGE = ("Percent change vs the previous period: (value - previous) / previous * 100. "
              "Null when the previous period is unavailable or its value is 0.")


class Period(BaseModel):
    start_date: dt.date
    end_date: dt.date
    days: int


class PreviousPeriod(Period):
    available: bool = Field(description="False when the previous period starts before the first date in the data; "
                                        "previous values and changes are then null.")


class CountMetric(BaseModel):
    value: int
    previous: int | None
    change_pct: float | None = Field(description=PCT_CHANGE)


class RateMetric(BaseModel):
    value: float | None
    previous: float | None
    change_pts: float | None = Field(
        description="Change in PERCENTAGE POINTS: (value - previous) * 100. Null when either rate is missing.")


class Kpis(BaseModel):
    """Overview KPIs for the filtered period and the immediately preceding period of equal length
    (same countries and categories)."""

    period: Period
    previous_period: PreviousPeriod
    unique_videos: CountMetric = Field(
        description="VIDEO-LEVEL: COUNT(DISTINCT video_id) among filtered snapshots.")
    trending_volume: CountMetric = Field(
        description="SNAPSHOT-LEVEL: number of filtered snapshot rows (country x video x day appearances).")
    views: CountMetric = Field(
        description="VIDEO-LEVEL: sum of view_count from each video's latest snapshot within the filtered "
                    "dataset, counted once per video. Views are never summed across historical snapshots. "
                    "View counts are lifetime totals, so the change compares the videos trending in each "
                    "period, not views gained.")
    unique_channels: CountMetric = Field(
        description="SNAPSHOT-LEVEL: distinct channels among filtered snapshots.")
    engagement_rate: RateMetric = Field(
        description="VIDEO-LEVEL: (SUM(likes) + SUM(comments)) / SUM(views) over the same latest snapshots. "
                    "Change is in percentage points.")


class DailyPoint(BaseModel):
    date: dt.date
    trending_volume: int = Field(description="SNAPSHOT-LEVEL: snapshots on this date.")
    unique_videos: int = Field(description="VIDEO-LEVEL: distinct videos on this date (a video trending in "
                                           "several selected countries that day counts once).")


class DailySeries(BaseModel):
    key: str | None = Field(description="Country code or category for split series; null when not split.")
    points: list[DailyPoint] = Field(description="Every calendar date in the range, zero-filled.")


class DailyVolume(BaseModel):
    """Daily trending activity. No daily views: view counts are cumulative lifetime totals."""

    split_by: Literal["country", "category"] | None
    series: list[DailySeries]
