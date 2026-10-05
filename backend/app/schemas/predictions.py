"""Prediction request/response models.

API validation here covers only types, lengths and bounds. Model-specific input
normalization (category ID -> name, case-insensitive matching, supported countries and
categories) stays in the frozen ml/ package and its errors are returned as 422.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints

Tag = Annotated[str, StringConstraints(max_length=100)]


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=200)
    description: str = Field("", max_length=5000)
    tags: list[Tag] = Field(default_factory=list, max_length=50,
                            description="Joined with ',' before reaching the model (the stored tag format).")
    channel_title: str = Field("", max_length=200)
    category: Annotated[str, StringConstraints(max_length=64)] | StrictInt = Field(
        description="Category name (e.g. 'Sports') or YouTube category ID (e.g. 17). "
                    "See /api/v1/predictions/model-info for supported values.")
    country: str = Field(max_length=8, description="Country code; see model-info for supported values.")
    duration_sec: float = Field(ge=0, le=604800, allow_inf_nan=False)
    channel_subscriber_count: int = Field(ge=0, le=10**10)
    channel_video_count: int = Field(ge=0, le=10**8)
    channel_view_count: int = Field(ge=0, le=10**13)


class PredictionComponents(BaseModel):
    text: float = Field(description="Text sub-model (LaBSE embedding of channel, title, description, tags).")
    channel_and_numeric: float = Field(description="Channel statistics, duration, category and country sub-model.")
    psychology: float = Field(description="Title-signal sub-model (see model-info limitations).")


class PredictionInputsUsed(BaseModel):
    category: str = Field(description="Category name sent to the model (IDs are converted).")
    country: str


class PredictionModelRef(BaseModel):
    version: str
    label_definition: str


class Prediction(BaseModel):
    high_performance_probability: float = Field(
        description="Model score that a video which IS ALREADY TRENDING performs at or above its country's "
                    "thresholds for views, likes and comments. It is NOT a probability that an arbitrary "
                    "video will become trending.")
    components: PredictionComponents
    inputs_used: PredictionInputsUsed
    model: PredictionModelRef


class ModelInfo(BaseModel):
    name: str
    version: str
    output: str
    label_definition: str
    not_a_prediction_of: str
    training_data: str
    supported_countries: list[str]
    supported_categories: list[str]
    category_input: str
    components: dict[str, str]
    reported_metrics: dict[str, str]
    limitations: list[str]
