"""Prediction service: lifecycle and API mapping around ml.TrendingPredictor (model v3).

Owns: loading one predictor instance, serializing inference calls, mapping the API
request to ml.PredictionInput, and describing the result honestly. Model behaviour and
features live in the ml/ package; training and evaluation in ml_training/.
"""

import hashlib
import logging
import threading
import time
from pathlib import Path

from app.core.errors import ModelUnavailableError

logger = logging.getLogger("app.predictions")

LOADED, NOT_LOADED, DISABLED, FAILED = "loaded", "not_loaded", "disabled", "failed"

LABEL_DEFINITION = (
    "Trained only on videos that were already on a YouTube trending list. A video is labelled "
    "high-performing in a country when, at its first trending appearance in that country, its likes "
    "and comments are at or above that country's median and its views are at or above "
    "100,000 x (country median views / India median views); medians are taken over all first "
    "trending appearances in each country."
)
NOT_A_PREDICTION_OF = (
    "It does not estimate whether an arbitrary video will reach a trending list; it scores how likely "
    "a video, if it is trending, is to be among the higher performers in its country."
)


class PredictionService:
    def __init__(self, enabled: bool, artifact_path=None):
        self.enabled = enabled
        self.artifact_path = artifact_path
        self.status = NOT_LOADED if enabled else DISABLED
        self.load_seconds = None
        self.version = None
        self._predictor = None
        self._lock = threading.Lock()  # one inference (and one load) at a time

    # ---------------- lifecycle ----------------
    def load(self) -> None:
        """Load the predictor once. Failures are logged and recorded, never raised,
        so the rest of the API stays available."""
        if not self.enabled:
            return
        with self._lock:
            if self.status == LOADED:
                return
            started = time.perf_counter()
            try:
                from ml import TrendingPredictor
                predictor = TrendingPredictor(artifact_path=self.artifact_path)
                self.version = _artifact_version(predictor.artifact_path)
                self._predictor = predictor
                self.status = LOADED
            except Exception:
                logger.exception("prediction model failed to load")
                self.status = FAILED
            self.load_seconds = round(time.perf_counter() - started, 2)
            logger.info("prediction model status=%s load_seconds=%s", self.status, self.load_seconds)

    def _require(self):
        if self.status == NOT_LOADED:  # lazy loading when ML_PRELOAD is false
            self.load()
        if self.status != LOADED:
            raise ModelUnavailableError(
                "The prediction model is disabled." if self.status == DISABLED
                else "The prediction model is not available.")
        return self._predictor

    def health(self) -> dict:
        return {"status": self.status, "load_seconds": self.load_seconds, "version": self.version}

    # ---------------- API operations ----------------
    def predict(self, request) -> dict:
        """request: schemas.predictions.PredictionRequest. ml.InvalidInputError propagates (-> 422)."""
        from ml import PredictionInput

        predictor = self._require()
        model_input = PredictionInput(
            category=request.category,
            country=request.country,
            video_duration_sec=request.duration_sec,
            channel_subscriber_count=request.channel_subscriber_count,
            channel_video_count=request.channel_video_count,
            channel_view_count=request.channel_view_count,
            video_title=request.title,
            video_description=request.description,
            video_tags=",".join(request.tags),
            channel_title=request.channel_title,
        )
        with self._lock:
            result = predictor.predict(model_input)
        return {
            "high_performance_probability": result.final_probability,
            "components": {"text": result.text_score},
            "inputs_used": {"category": result.category, "country": result.country},
            "model": {"version": self.version, "label_definition": LABEL_DEFINITION},
        }

    def model_info(self) -> dict:
        predictor = self._require()
        return {
            "name": "YouTube trending high-performance model (v3)",
            "version": self.version,
            "output": "high_performance_probability",
            "label_definition": LABEL_DEFINITION,
            "not_a_prediction_of": NOT_A_PREDICTION_OF,
            "training_data": "Trending videos from AU, CA, GB, IE, IN, NZ, US and ZA, 2024-10-12 to "
                             f"{predictor.trained_until}, one row per video and country (its first trending "
                             "appearance in that country).",
            "supported_countries": list(predictor.supported_countries),
            "supported_categories": list(predictor.supported_categories),
            "category_input": "Category name (case-insensitive) or YouTube category ID; IDs are converted "
                              "to names. Categories the model was not trained on are rejected.",
            "components": {
                "text": "Text score: logistic regression on the LaBSE embedding of channel name, title, "
                        "description and tags (only the first 256 tokens are read).",
                "high_performance_probability": "Gradient-boosting model on channel statistics, duration, "
                                                "category, country, title/description/tag signals and the "
                                                "text (text score plus 32 embedding components).",
            },
            "reported_metrics": {
                "roc_auc": "0.923",
                "roc_auc_live": "0.891",
                "note": "ROC-AUC on the newest held-out period (2025-12-03 to 2026-01-05, 26,300 video-country "
                        "rows), never used for training or model choice; the previous model scored 0.842 on the "
                        "same rows. Live: 397 videos on YouTube's trending lists on 2026-10-05 (previous model 0.832).",
            },
            "limitations": [
                "Only videos already trending were used for training; the score is not a trending-entry probability.",
                "Singapore (SG) and categories absent from training are not supported.",
                "Channel statistics are those of the time the video was trending, as in the training data.",
                "The share of high performers changes over time; probabilities can be too low or too high for "
                "a new period and are best read as relative indicators.",
                "Text beyond LaBSE's 256-token limit is ignored, so tags can be cut off by a long description.",
            ],
        }


def _artifact_version(artifact_path) -> str:
    """Short, stable identifier of the loaded model (first 12 hex digits of its SHA-256)."""
    return hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()[:12]
