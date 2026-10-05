"""Overview endpoints. Routes call app/repositories/overview.py directly."""

from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AppliedFiltersDep, DbConnection
from app.repositories import overview
from app.schemas.common import ERROR_RESPONSES, LATEST_SNAPSHOT_NOTE, AppliedFilters, FilteredResponse
from app.schemas.overview import DailyVolume, Kpis

router = APIRouter(prefix="/overview", tags=["overview"], responses=ERROR_RESPONSES)

# Built from the repository whitelist (single source of truth).
DailySplit = Enum("DailySplit", {k: k for k in overview.DAILY_SPLITS if k is not None}, type=str)


@router.get("/kpis", response_model=FilteredResponse[Kpis], summary="Overview KPIs with period-over-period change",
            description=LATEST_SNAPSHOT_NOTE + " Counts and views change in percent; engagement_rate changes "
                        "in percentage points. The previous period is the immediately preceding period of "
                        "equal length with the same countries and categories.")
def kpis(conn: DbConnection, filters: AppliedFiltersDep):
    return {"filters": AppliedFilters.from_filters(filters), "data": overview.get_kpis(conn, filters)}


@router.get("/daily-volume", response_model=FilteredResponse[DailyVolume],
            summary="Daily trending volume and unique videos (zero-filled)")
def daily_volume(conn: DbConnection, filters: AppliedFiltersDep,
                 split_by: Annotated[DailySplit | None, Query(
                     description="Split into one series per country or per (snapshot) category.")] = None):
    return {"filters": AppliedFilters.from_filters(filters),
            "data": overview.get_daily_volume(conn, filters, split_by.value if split_by else None)}
