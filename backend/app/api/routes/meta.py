"""Filter metadata."""

from fastapi import APIRouter

from app.api.deps import DbConnection
from app.repositories import meta
from app.repositories.filters import build_filters
from app.schemas.common import ERROR_RESPONSES, DataResponse
from app.schemas.meta import FilterOptions

router = APIRouter(prefix="/meta", tags=["metadata"], responses=ERROR_RESPONSES)


@router.get("/filters", response_model=DataResponse[FilterOptions],
            summary="Available countries, categories, date range and the default window")
def filter_options(conn: DbConnection):
    """All values come from PostgreSQL (app.trending_snapshots); nothing is hardcoded and the
    date boundaries come from the data, not today's date."""
    min_date, max_date = meta.get_date_range(conn)
    default = build_filters(conn)  # the same default window every filtered endpoint uses
    return {"data": {
        "countries": meta.get_countries(conn),
        "categories": meta.get_categories(conn),
        "date_range": {"min_date": min_date, "max_date": max_date},
        "default_range": {"start_date": default.start_date, "end_date": default.end_date, "days": default.days},
    }}
