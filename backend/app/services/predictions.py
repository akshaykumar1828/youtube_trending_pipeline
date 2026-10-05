"""Prediction service: lifecycle and API mapping around the frozen ml.TrendingPredictor.

Owns: loading one predictor instance, serializing inference calls, mapping the API
request to ml.PredictionInput, and describing the result honestly. It does NOT
change any model behaviour or preprocessing (those stay in the frozen ml/ package)
and never imports the legacy predictor.py or Streamlit.
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
    "high-performing when, at its first trending appearance, its likes and comments are at or above "
    "its country's median and its views are at or above 100,000 x (country median views / India "
    "median views)."
)
NOT_A_PREDICTION_OF = (
    "It does not estimate whether an arbitrary video will reach a trending list; it scores how likely "
    "a video, if it is trending, is to be among the higher performers in its country."
)


class PredictionService:
    def __init__(self, enabled: bool, artifact_dir=None):
        self.enabled = enabled
        self.artifact_dir = artifact_dir
        self.status = NOT_LOADED if enabled else DISABLED
        self.load_seconds = None
        self.version = None
        self._predictor = None
        self._lock = threading.Lock()  # one inference (and one load) at a time

    # ---------------- lifecycle ----------------
    def load(self) -> None:
        """Load the frozen predictor once. Failures are logged and recorded, never raised,
        so the rest of the API stays available."""
        if not self.enabled:
            return
        with self._lock:
            if self.status == LOADED:
                return
            started = time.perf_counter()
            try:
                from ml import TrendingPredictor
                predictor = TrendingPredictor(artifact_dir=self.artifact_dir)
                self.version = _artifact_version(predictor.artifact_dir)
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
            "components": {
                "text": result.text_score,
                "channel_and_numeric": result.numeric_score,
                "psychology": result.psychology_score,
            },
            "inputs_used": {"category": result.category, "country": result.country},
            "model": {"version": self.version, "label_definition": LABEL_DEFINITION},
        }

    def model_info(self) -> dict:
        predictor = self._require()
        return {
            "name": "YouTube trending high-performance model (frozen)",
            "version": self.version,
            "output": "high_performance_probability",
            "label_definition": LABEL_DEFINITION,
            "not_a_prediction_of": NOT_A_PREDICTION_OF,
            "training_data": "Trending videos from AU, CA, GB, IE, IN, NZ, US and ZA, "
                             "2024-10-12 to 2026-01-05, one row per video (first trending appearance).",
            "supported_countries": list(predictor.supported_countries),
            "supported_categories": list(predictor.supported_categories),
            "category_input": "Category name (case-insensitive) or YouTube category ID; IDs are converted "
                              "to names. Categories the model was not trained on are rejected.",
            "components": {
                "text": "Logistic regression on LaBSE embeddings of channel title, title, description and tags.",
                "channel_and_numeric": "Calibrated random forest on channel statistics, duration, category and country.",
                "psychology": "Logistic regression on title signals.",
                "high_performance_probability": "Logistic-regression combination of the three component scores.",
            },
            "reported_metrics": {
                "roc_auc": "0.894",
                "note": "Reported in the training notebook on a held-out split computed with the uncalibrated "
                        "random forest; the served pipeline (calibrated forest) has not been separately evaluated.",
            },
            "limitations": [
                "Only videos already trending were used for training; the score is not a trending-entry probability.",
                "Singapore (SG) and categories absent from training are not supported.",
                "The urgency, hype, official and emotion keyword flags and the title-description overlap are "
                "fixed at 0 at inference (as in the original application); only digits, '?' and '!' in the "
                "title vary the psychology component.",
                "The combining model was trained on uncalibrated random-forest scores but receives calibrated "
                "scores at inference; the model is served as-is without retraining.",
                "Scores reflect the 2024-2026 training distribution and are best read as relative indicators.",
                "The random forest evaluates trees in parallel, so repeated predictions can differ at ~1e-16.",
            ],
        }


def _artifact_version(artifact_dir) -> str:
    """Short, stable identifier of the loaded artifacts (hash of each .pkl file's SHA-256)."""
    combined = hashlib.sha256()
    for path in sorted(Path(artifact_dir).glob("*.pkl")):
        combined.update(path.name.encode())
        combined.update(hashlib.sha256(path.read_bytes()).digest())
    return combined.hexdigest()[:12]
