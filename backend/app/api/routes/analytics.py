"""Analytics endpoints. Routes call app/repositories/analytics.py directly."""

from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AppliedFiltersDep, DbConnection
from app.repositories import analytics
from app.schemas.analytics import CategoryPerformance, ChannelPerformance, CountryPerformance, EngagementAnalysis
from app.schemas.common import ERROR_RESPONSES, LATEST_SNAPSHOT_NOTE, AppliedFilters, FilteredResponse

router = APIRouter(prefix="/analytics", tags=["analytics"], responses=ERROR_RESPONSES)

ChannelSort = Enum("ChannelSort", {k: k for k in analytics.CHANNEL_SORTS}, type=str)


@router.get("/categories", response_model=FilteredResponse[list[CategoryPerformance]],
            summary="Category performance",
            description="Snapshot-level volume uses each snapshot's own category; video-level metrics use the "
                        "category of each video's latest snapshot. " + LATEST_SNAPSHOT_NOTE)
def categories(conn: DbConnection, filters: AppliedFiltersDep):
    return {"filters": AppliedFilters.from_filters(filters),
            "data": analytics.get_category_performance(conn, filters)}


@router.get("/countries", response_model=FilteredResponse[list[CountryPerformance]],
            summary="Country performance",
            description="Country-level metrics use each video's latest filtered snapshot in that country. "
                        "views_of_trending_videos are GLOBAL lifetime views of videos that trended in the "
                        "country: not views from the country and not additive across countries.")
def countries(conn: DbConnection, filters: AppliedFiltersDep):
    return {"filters": AppliedFilters.from_filters(filters),
            "data": analytics.get_country_performance(conn, filters)}


@router.get("/engagement", response_model=FilteredResponse[EngagementAnalysis],
            summary="Engagement totals, distribution, histogram, by-category spread and top-views scatter",
            description=LATEST_SNAPSHOT_NOTE)
def engagement(conn: DbConnection, filters: AppliedFiltersDep,
               scatter_limit: Annotated[int, Query(ge=1, le=analytics.MAX_SCATTER,
                                                   description="Top videos by views in the scatter.")] = 200):
    return {"filters": AppliedFilters.from_filters(filters),
            "data": analytics.get_engagement_analysis(conn, filters, scatter_limit=scatter_limit)}


@router.get("/channels", response_model=FilteredResponse[list[ChannelPerformance]],
            summary="Top channels", description=LATEST_SNAPSHOT_NOTE)
def channels(conn: DbConnection, filters: AppliedFiltersDep,
             sort: Annotated[ChannelSort, Query(description="Ranking metric (descending).")] = ChannelSort("unique_videos"),
             limit: Annotated[int, Query(ge=1, le=analytics.MAX_CHANNELS)] = 10):
    return {"filters": AppliedFilters.from_filters(filters),
            "data": analytics.get_top_channels(conn, filters, sort=sort.value, limit=limit)}
