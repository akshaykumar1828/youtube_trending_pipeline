"""Filter metadata response models."""

import datetime as dt

from pydantic import BaseModel, Field


class CountryOption(BaseModel):
    code: str
    name: str


class DateRange(BaseModel):
    min_date: dt.date
    max_date: dt.date


class DefaultRange(BaseModel):
    start_date: dt.date
    end_date: dt.date
    days: int


class FilterOptions(BaseModel):
    countries: list[CountryOption] = Field(description="Countries present in the data.")
    categories: list[str] = Field(description="Categories present in the data ('Unknown' = missing category).")
    date_range: DateRange = Field(description="Earliest and latest trending dates in the data.")
    default_range: DefaultRange = Field(
        description="Default window used when no dates are given: 30 days ending at the latest trending date.")
