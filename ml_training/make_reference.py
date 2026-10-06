"""Create tests/fixtures/reference_predictions.json for the app's model and prove that the
app's inference code (ml/) reproduces the TRAINING pipeline exactly.

Expected values are computed with the training code path (train_v3.predict: batch feature
table + model) and compared with ml.TrendingPredictor (the app's per-request path) on the same
inputs and LaBSE embeddings. Any difference would come from the serving code and must be ~0.

    python make_reference.py      (system Python: CPU is enough for 25 videos)
"""

import throttle  # noqa: F401  (first)

import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from common import REPO
from train_v3 import predict as training_predict

sys.path.insert(0, str(REPO))
from ml import PredictionInput, TrendingPredictor  # noqa: E402
from ml.schemas import YOUTUBE_CATEGORY_IDS  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "reference_predictions.json"
ARTIFACT = REPO / "model" / "trending_model_v3.joblib"


def main():
    inputs = [c for c in json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]]
    predictor = TrendingPredictor(ARTIFACT)
    model = joblib.load(ARTIFACT)

    df = pd.DataFrame([c["input"] for c in inputs])
    df["video_category_id"] = [YOUTUBE_CATEGORY_IDS.get(str(v), v) for v in df["video_category_id"]]
    for col in ("video_duration_sec", "channel_subscriber_count", "channel_video_count", "channel_view_count"):
        df[col] = df[col].astype(float)
    from ml.features import texts
    # One text at a time, exactly like the API (batching changes LaBSE output by ~1e-7).
    emb = np.vstack([predictor.embedder.encode([t], convert_to_numpy=True, show_progress_bar=False)
                     for t in texts(df)])

    # training-side prediction (ml_training feature code)
    expected = training_predict(model, df, emb)
    text_expected = model["text_model"].predict_proba(emb)[:, 1]

    cases, worst = [], 0.0
    for i, case in enumerate(inputs):
        inp = case["input"]
        result = predictor.predict(PredictionInput(
            category=inp["video_category_id"], country=inp["country"],
            video_duration_sec=inp["video_duration_sec"], channel_subscriber_count=inp["channel_subscriber_count"],
            channel_video_count=inp["channel_video_count"], channel_view_count=inp["channel_view_count"],
            video_title=inp["video_title"], video_description=inp["video_description"],
            video_tags=inp["video_tags"], channel_title=inp["channel_title"]))
        worst = max(worst, abs(result.final_probability - expected[i]), abs(result.text_score - text_expected[i]))
        cases.append({"name": case["name"], "input": inp,
                      "expected": {"high_performance_probability": float(expected[i]),
                                   "text_score": float(text_expected[i]),
                                   "category": result.category, "country": result.country}})
    print(f"largest difference app vs training pipeline: {worst:.3e}")
    if worst > 1e-9:
        raise SystemExit("app inference does NOT match the training pipeline")
    FIXTURE.write_text(json.dumps({
        "generated_by": "ml_training/make_reference.py (training pipeline; verified equal to ml/ inference)",
        "model": ARTIFACT.name,
        "model_sha256": hashlib.sha256(ARTIFACT.read_bytes()).hexdigest(),
        "cases": cases,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} reference cases to {FIXTURE.relative_to(REPO)}")


if __name__ == "__main__":
    main()
