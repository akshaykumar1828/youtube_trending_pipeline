"""Shared response envelopes."""

import datetime as dt
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

LATEST_SNAPSHOT_NOTE = (
    "'Latest snapshot' means each video's latest snapshot WITHIN THE FILTERED DATASET "
    "(the rows matching the date range, countries and categories), not its globally latest snapshot."
)


class AppliedFilters(BaseModel):
    """The filters actually applied after validation and defaults (default window: 30 days
    ending at the database's latest trending date). Empty country/category lists mean all."""

    start_date: dt.date
    end_date: dt.date
    days: int
    countries: list[str] = Field(description="Applied country codes; empty = all countries.")
    categories: list[str] = Field(description="Applied categories; empty = all categories.")

    @classmethod
    def from_filters(cls, filters) -> "AppliedFilters":
        return cls(start_date=filters.start_date, end_date=filters.end_date, days=filters.days,
                   countries=list(filters.countries), categories=list(filters.categories))


class DataResponse(BaseModel, Generic[T]):
    data: T


class FilteredResponse(BaseModel, Generic[T]):
    filters: AppliedFilters
    data: T


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str
    field: str | None = None
    request_id: str | None = Field(None, description="Same value as the X-Request-ID response header.")
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


ERROR_RESPONSES = {
    422: {"model": ErrorResponse, "description": "Invalid request, filter or parameter."},
    500: {"model": ErrorResponse, "description": "Unexpected server or database error."},
    503: {"model": ErrorResponse, "description": "Database unavailable or busy."},
    504: {"model": ErrorResponse, "description": "Database statement timeout."},
}
