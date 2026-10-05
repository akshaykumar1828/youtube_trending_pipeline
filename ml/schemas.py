"""Input/output types and input validation for the frozen trending model.

Validation and the category-ID adapter run BEFORE the model. They never change
the saved encoder or model; they only reject inputs the model was not trained
on, or translate a YouTube category ID into the category name the encoder expects.
"""

import math
from dataclasses import dataclass, field
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

# Encoder category created from missing training data; not a valid user input.
MISSING_DATA_CATEGORY = "None"

TEXT_FIELDS = ("video_title", "video_description", "video_tags", "channel_title")
NUMERIC_FIELDS = (
    "video_duration_sec",
    "channel_subscriber_count",
    "channel_video_count",
    "channel_view_count",
)


class InvalidInputError(ValueError):
    """Raised when a prediction input is not supported by the frozen model."""

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

    @classmethod
    def from_legacy_dict(cls, data):
        """Build from the dict format accepted by the legacy predict_trending()."""
        return cls(
            category=data["video_category_id"],
            country=data["country"],
            video_duration_sec=data["video_duration_sec"],
            channel_subscriber_count=data["channel_subscriber_count"],
            channel_video_count=data["channel_video_count"],
            channel_view_count=data["channel_view_count"],
            video_title=data.get("video_title", ""),
            video_description=data.get("video_description", ""),
            video_tags=data.get("video_tags", ""),
            channel_title=data.get("channel_title", ""),
        )


@dataclass
class PredictionResult:
    final_probability: float
    text_score: float
    numeric_score: float
    psychology_score: float
    category: str  # category name actually sent to the encoder
    country: str
    features: dict = field(default_factory=dict)

    def to_legacy_dict(self):
        """Same keys and rounding as the legacy predict_trending() return value."""
        return {
            "final_probability": round(self.final_probability, 4),
            "text_score": round(self.text_score, 4),
            "numeric_score": round(self.numeric_score, 4),
            "psychology_score": round(self.psychology_score, 4),
        }


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
