"""Inference for the YouTube trending model (v3).

One gradient-boosting model scores a video in a given country from channel statistics,
duration, category, country, title/description/tag signals and the text (LaBSE embedding:
a logistic-regression text score plus 32 PCA components). Training code and evaluation:
ml_training/ (see ml_training/REPORT.md). The artifact is only read, never re-saved.
"""

import os
from pathlib import Path

import joblib
import pandas as pd

from . import features
from .schemas import MISSING_DATA_CATEGORY, PredictionInput, PredictionResult, validate

DEFAULT_ARTIFACT = Path(__file__).resolve().parent.parent / "model" / "trending_model_v3.joblib"
LABSE_MODEL = "sentence-transformers/LaBSE"
LABSE_REVISION = "836121a0533e5664b21c7aacc5d22951f2b8b25b"


class TrendingPredictor:
    """Loads the model artifact and LaBSE once; call predict() per video."""

    def __init__(self, artifact_path=None, device="cpu"):
        # Imported here so `import ml` stays light (no torch) until a predictor is built.
        from sentence_transformers import SentenceTransformer

        path = Path(artifact_path or os.getenv("ML_ARTIFACT_PATH") or DEFAULT_ARTIFACT)
        self.artifact_path = path
        model = joblib.load(path)
        self.text_model = model["text_model"]
        self.pca = model["pca"]
        self.gbm = model["gbm"]
        self.vpv_clip, self.spv_clip = model["clips"]
        self.columns = model["columns"]
        self.categories = model["categories"]
        self.trained_until = model["trained_until"]

        self.embedder = SentenceTransformer(LABSE_MODEL, device=device, revision=LABSE_REVISION)

        # Supported values come from the training data, not a hand-written list.
        self.supported_categories = tuple(c for c in self.categories["video_category_id"]
                                          if c != MISSING_DATA_CATEGORY)
        self.supported_countries = tuple(self.categories["country"])

    def predict(self, data: PredictionInput) -> PredictionResult:
        category, country = validate(data, self.supported_categories, self.supported_countries)
        row = pd.DataFrame([{
            "video_title": data.video_title, "video_description": data.video_description,
            "video_tags": data.video_tags, "channel_title": data.channel_title,
            "video_category_id": category, "country": country,
            "video_duration_sec": float(data.video_duration_sec),
            "channel_subscriber_count": float(data.channel_subscriber_count),
            "channel_video_count": float(data.channel_video_count),
            "channel_view_count": float(data.channel_view_count),
        }])

        embedding = self.embedder.encode(features.texts(row), convert_to_numpy=True, show_progress_bar=False)
        text_probability = self.text_model.predict_proba(embedding)[:, 1]
        table = features.model_table(row, self.vpv_clip, self.spv_clip, text_probability,
                                     self.pca.transform(embedding))
        for column, cats in self.categories.items():
            table[column] = pd.Categorical(table[column].astype(str), categories=cats)
        probability = self.gbm.predict_proba(table[self.columns])[:, 1][0]

        return PredictionResult(
            final_probability=float(probability),
            text_score=float(text_probability[0]),
            category=category,
            country=country,
        )
