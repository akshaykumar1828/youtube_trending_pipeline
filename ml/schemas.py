"""Input/output types and input validation for the trending model.

Validation and the category-ID adapter run BEFORE the model. They only reject inputs
the model was not trained on, or translate a YouTube category ID into the category
name the model expects.
"""

import math
from dataclasses import dataclass
from numbers import Real


# YouTube Data API assignable video category IDs -> names.
# Used only as an input adapter; names the model was not trained on are rejected.
YOUTUBE_CATEGORY_IDS = {
    "1": "Film & Animation",
    "2": "Autos & Vehicles",
    "10": "Music",
    "15": "Pets & Animals",
    "17": "Sports",
    "19": "Travel & Events",
    "20": "Gaming",
    "22": "People & Blogs",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "News & Politics",
    "26": "Howto & Style",
    "27": "Education",
    "28": "Science & Technology",
    "29": "Nonprofits & Activism",
}

# Category used in the training data for videos without one; not a valid user input.
MISSING_DATA_CATEGORY = "None"

TEXT_FIELDS = ("video_title", "video_description", "video_tags", "channel_title")
NUMERIC_FIELDS = (
    "video_duration_sec",
    "channel_subscriber_count",
    "channel_video_count",
    "channel_view_count",
)


class InvalidInputError(ValueError):
    """Raised when a prediction input is not supported by the model."""

    def __init__(self, errors):
        self.errors = errors  # list of {"field": str, "message": str}
        super().__init__("; ".join(f"{e['field']}: {e['message']}" for e in errors))


@dataclass
class PredictionInput:
    category: object  # category name (e.g. "Sports") or YouTube category ID (e.g. "17" / 17)
    country: str      # ISO country code, e.g. "IN"
    video_duration_sec: Real
    channel_subscriber_count: Real
    channel_video_count: Real
    channel_view_count: Real
    video_title: str = ""
    video_description: str = ""
    video_tags: str = ""
    channel_title: str = ""


@dataclass
class PredictionResult:
    final_probability: float  # high_performance_probability
    text_score: float         # text model's probability from title, description, tags and channel name
    category: str             # category name actually used by the model
    country: str


def resolve_category(value, supported_categories):
    """Return the encoder category name for a name or YouTube category ID."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise InvalidInputError([{"field": "category", "message": "must be a category name or YouTube category ID"}])

    raw = str(value).strip()
    supported = ", ".join(supported_categories)

    if raw.isdigit():
        name = YOUTUBE_CATEGORY_IDS.get(raw)
        if name is None:
            raise InvalidInputError([{"field": "category", "message": f"unknown YouTube category ID '{raw}'. Supported categories: {supported}"}])
        if name not in supported_categories:
            raise InvalidInputError([{"field": "category", "message": f"category ID '{raw}' ({name}) is not supported by the model. Supported categories: {supported}"}])
        return name

    by_lower = {c.lower(): c for c in supported_categories}
    name = by_lower.get(raw.lower())
    if name is None:
        raise InvalidInputError([{"field": "category", "message": f"unsupported category '{raw}'. Supported categories: {supported}"}])
    return name


def resolve_country(value, supported_countries):
    """Return the normalised country code if the model supports it."""
    code = value.strip().upper() if isinstance(value, str) else None
    if code not in supported_countries:
        raise InvalidInputError([{"field": "country", "message": f"unsupported country {value!r}. Supported countries: {', '.join(supported_countries)}"}])
    return code


def validate(data, supported_categories, supported_countries):
    """Validate a PredictionInput. Returns (category_name, country_code)."""
    errors = []

    for name in TEXT_FIELDS:
        if not isinstance(getattr(data, name), str):
            errors.append({"field": name, "message": "must be a string"})

    for name in NUMERIC_FIELDS:
        v = getattr(data, name)
        if isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) or v < 0:
            errors.append({"field": name, "message": "must be a finite number >= 0"})

    category = country = None
    try:
        category = resolve_category(data.category, supported_categories)
    except InvalidInputError as e:
        errors.extend(e.errors)
    try:
        country = resolve_country(data.country, supported_countries)
    except InvalidInputError as e:
        errors.extend(e.errors)

    if errors:
        raise InvalidInputError(errors)
    return category, country
