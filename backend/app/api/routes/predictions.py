"""Prediction endpoints (ML model v3 via services/predictions.py)."""

from fastapi import APIRouter

from app.api.deps import PredictionServiceDep
from app.schemas.common import DataResponse, ErrorResponse
from app.schemas.predictions import ModelInfo, Prediction, PredictionRequest

router = APIRouter(prefix="/predictions", tags=["predictions"], responses={
    422: {"model": ErrorResponse, "description": "Invalid or unsupported prediction input."},
    503: {"model": ErrorResponse, "description": "The prediction model is disabled or failed to load."},
})


@router.get("/model-info", response_model=DataResponse[ModelInfo],
            summary="What the model predicts, supported inputs and limitations")
def model_info(service: PredictionServiceDep):
    return {"data": service.model_info()}


@router.post("", response_model=DataResponse[Prediction], summary="Score a video's high-performance likelihood",
             description="Returns high_performance_probability: the model's score that a video which is "
                         "ALREADY TRENDING performs at or above its country's thresholds for views, likes and "
                         "comments. It is not the probability that an arbitrary video will become trending. "
                         "Nothing is stored.")
def predict(body: PredictionRequest, service: PredictionServiceDep):
    return {"data": service.predict(body)}
