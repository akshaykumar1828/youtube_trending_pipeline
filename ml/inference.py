"""Standalone inference for the frozen YouTube trending model.

Reproduces the legacy predictor.py pipeline without any Streamlit dependency.
Artifacts are only ever read (joblib.load); they are never refit or re-saved.
"""

import os
from pathlib import Path

import joblib
import numpy as np

from . import features
from .schemas import MISSING_DATA_CATEGORY, PredictionInput, PredictionResult, validate


DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "model"
LABSE_MODEL = "sentence-transformers/LaBSE"


class TrendingPredictor:
    """Loads the frozen model artifacts and LaBSE once; call predict() per video."""

    def __init__(self, artifact_dir=None, device="cpu"):
        # Imported here so `import ml` stays light (no torch) until a predictor is built.
        from sentence_transformers import SentenceTransformer

        artifact_dir = Path(artifact_dir or os.getenv("ML_ARTIFACT_DIR") or DEFAULT_ARTIFACT_DIR)
        self.artifact_dir = artifact_dir

        self.embedder = SentenceTransformer(LABSE_MODEL, device=device)

        self.text_scaler = joblib.load(artifact_dir / "text_scaler.pkl")
        self.text_lr = joblib.load(artifact_dir / "text_lr.pkl")
        self.rf_calibrated = joblib.load(artifact_dir / "rf_calibrated.pkl")
        self.psych_scaler = joblib.load(artifact_dir / "psych_scaler.pkl")
        self.psych_lr = joblib.load(artifact_dir / "psych_lr.pkl")
        self.meta_lr = joblib.load(artifact_dir / "meta_lr.pkl")
        self.ohe = joblib.load(artifact_dir / "ohe.pkl")

        clip_values = joblib.load(artifact_dir / "clip_values.pkl")
        self.vpv_clip = clip_values["vpv_clip"]
        self.spv_clip = clip_values["spv_clip"]

        # Supported values come from the saved encoder, not a hand-written list.
        categories, countries = self.ohe.categories_
        self.supported_categories = tuple(c for c in categories if c != MISSING_DATA_CATEGORY)
        self.supported_countries = tuple(countries)

    def predict(self, data: PredictionInput) -> PredictionResult:
        category, country = validate(data, self.supported_categories, self.supported_countries)

        # -----------------------
        # TEXT MODEL
        # -----------------------
        combined_text = features.build_text(
            data.channel_title, data.video_title, data.video_description, data.video_tags
        )
        text_emb = self.embedder.encode([combined_text], convert_to_numpy=True)
        text_emb = self.text_scaler.transform(text_emb)
        text_prob = self.text_lr.predict_proba(text_emb)[:, 1][0]

        # -----------------------
        # NUMERIC + CATEGORICAL MODEL
        # -----------------------
        num_features = features.numeric_features(
            data.video_duration_sec,
            data.channel_subscriber_count,
            data.channel_video_count,
            data.channel_view_count,
            self.vpv_clip,
            self.spv_clip,
        )
        cat_feature = self.ohe.transform(features.categorical_frame(category, country))
        rf_input = np.hstack([cat_feature, num_features])
        rf_prob = self.rf_calibrated.predict_proba(rf_input)[:, 1][0]

        # -----------------------
        # PSYCHOLOGY MODEL
        # -----------------------
        psych_raw = features.psych_features(data.video_title)
        psych_scaled = self.psych_scaler.transform(psych_raw)
        psych_prob = self.psych_lr.predict_proba(psych_scaled)[:, 1][0]

        # -----------------------
        # META STACKING MODEL
        # -----------------------
        final_prob = self.meta_lr.predict_proba(
            np.array([[text_prob, rf_prob, psych_prob]])
        )[:, 1][0]

        return PredictionResult(
            final_probability=float(final_prob),
            text_score=float(text_prob),
            numeric_score=float(rf_prob),
            psychology_score=float(psych_prob),
            category=category,
            country=country,
            features={
                "numeric": dict(zip(features.NUMERIC_FEATURES, num_features[0].tolist())),
                "psychology": dict(zip(features.PSYCH_FEATURES, psych_raw[0].tolist())),
            },
        )
