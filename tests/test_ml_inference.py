"""Tests for the ML inference layer (ml/, model v3).

They prove that the app's inference reproduces the training pipeline exactly (the reference
predictions were produced by ml_training/make_reference.py from the training code), that the
model file is the one that was evaluated, and that inputs are validated before the model.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

from ml import InvalidInputError, PredictionInput, TrendingPredictor  # noqa: E402
from ml import features  # noqa: E402

REFERENCE = json.loads((FIXTURES / "reference_predictions.json").read_text(encoding="utf-8"))
ARTIFACT_HASHES = json.loads((FIXTURES / "artifact_sha256.json").read_text(encoding="utf-8"))
CASES = REFERENCE["cases"]
CASE_IDS = [c["name"] for c in CASES]


def as_input(d):
    return PredictionInput(
        category=d["video_category_id"], country=d["country"], video_duration_sec=d["video_duration_sec"],
        channel_subscriber_count=d["channel_subscriber_count"], channel_video_count=d["channel_video_count"],
        channel_view_count=d["channel_view_count"], video_title=d["video_title"],
        video_description=d["video_description"], video_tags=d["video_tags"], channel_title=d["channel_title"])


# ---------------------------------------------------
# THE MODEL FILE IS THE EVALUATED ONE
# ---------------------------------------------------
def test_model_directory_matches_manifest():
    model_dir = ROOT / ARTIFACT_HASHES["directory"]
    actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(model_dir.iterdir())}
    assert actual == ARTIFACT_HASHES["files"]


def test_reference_predictions_belong_to_this_model():
    path = ROOT / "model" / REFERENCE["model"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == REFERENCE["model_sha256"]


def test_ml_code_never_writes_or_fits():
    pattern = re.compile(r"\b(dump|fit|fit_transform|partial_fit)\s*\(")
    for path in (ROOT / "ml").glob("*.py"):
        assert not pattern.search(path.read_text(encoding="utf-8")), path.name


def test_ml_package_has_no_ui_imports():
    for path in (ROOT / "ml").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "streamlit" not in text and "fastapi" not in text, path.name


# ---------------------------------------------------
# LOADING
# ---------------------------------------------------
@pytest.fixture(scope="session")
def predictor():
    return TrendingPredictor()


def test_model_loads(predictor):
    assert predictor.embedder.get_embedding_dimension() == 768
    assert predictor.pca.n_components_ == 32
    assert predictor.gbm.n_features_in_ == len(predictor.columns)
    assert predictor.trained_until == "2026-07-19"


def test_second_model_has_no_channel_numbers(predictor):
    assert predictor.gbm_no_channel.n_features_in_ == len(predictor.columns_no_channel)
    assert set(predictor.columns) - set(predictor.columns_no_channel) == set(features.CHANNEL_NUMBER_FEATURES)
    assert predictor.blend_weight == 0.5


def test_blend_halves_the_channel_models_swing():
    """With weight 0.5 the final logit is the average of the two models' logits: since the
    second model never sees channel numbers, a wrong channel input moves the final logit by
    exactly half of what it moves the channel model's logit."""
    z = lambda p: float(features.logit(p)[0])
    p_full, p_wrong, p_no_channel = 0.80, 0.20, 0.60
    good = features.blend([p_full], [p_no_channel], 0.5)
    wrong = features.blend([p_wrong], [p_no_channel], 0.5)
    assert z(good) == pytest.approx((z([p_full]) + z([p_no_channel])) / 2)
    assert z(good) - z(wrong) == pytest.approx((z([p_full]) - z([p_wrong])) / 2)


def test_feature_table_matches_model_columns(predictor):
    row = pd.DataFrame([{**CASES[0]["input"], "video_category_id": "Sports"}])
    table = features.model_table(row, predictor.vpv_clip, predictor.spv_clip, [0.5],
                                 predictor.pca.transform(predictor.embedder.encode(features.texts(row))))
    assert list(table.columns) == predictor.columns


def test_supported_values_come_from_training_data(predictor):
    assert predictor.supported_countries == ("AU", "CA", "GB", "IE", "IN", "NZ", "US", "ZA")
    assert "None" not in predictor.supported_categories
    assert len(predictor.supported_categories) == 15
    assert "Nonprofits & Activism" in predictor.supported_categories


# ---------------------------------------------------
# PARITY WITH THE TRAINING PIPELINE
# ---------------------------------------------------
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_matches_reference_predictions(predictor, case):
    result = predictor.predict(as_input(case["input"]))
    expected = case["expected"]
    assert abs(result.final_probability - expected["high_performance_probability"]) <= 1e-9
    assert abs(result.text_score - expected["text_score"]) <= 1e-9
    assert (result.category, result.country) == (expected["category"], expected["country"])


def test_predictions_are_deterministic(predictor):
    a = predictor.predict(as_input(CASES[0]["input"]))
    b = predictor.predict(as_input(CASES[0]["input"]))
    assert a == b


def test_country_changes_the_prediction(predictor):
    base = CASES[0]["input"]
    probs = {c: predictor.predict(as_input({**base, "country": c})).final_probability for c in ("IN", "AU", "GB")}
    assert len({round(p, 6) for p in probs.values()}) == 3


# ---------------------------------------------------
# FEATURES
# ---------------------------------------------------
def _content(title="", description="", tags=""):
    df = pd.DataFrame([{"video_title": title, "video_description": description, "video_tags": tags}])
    return features.content_features(df).iloc[0].to_dict()


def test_question_and_exclamation_marks_are_seen():
    c = _content("Why is this happening?! 2025")
    assert c["title_has_question"] == 1 and c["title_has_exclamation"] == 1 and c["title_has_digit"] == 1


def test_keywords_match_whole_words_only():
    assert _content("Breaking news today")["kw_urgency"] == 1
    assert _content("You know what we delivered")["kw_urgency"] == 0   # 'now' / 'live' inside other words


def test_tags_split_on_commas():
    assert _content(tags="india vs australia,cricket, highlights")["tag_count"] == 3


def test_text_order_and_cleaning():
    assert features.build_text("Star Sports", "Final Over!", "Watch now.", "a,b") == "star sports final over watch now ab"


# ---------------------------------------------------
# VALIDATION
# ---------------------------------------------------
def _input(**overrides):
    base = dict(category="Sports", country="IN", video_duration_sec=140,
                channel_subscriber_count=1000, channel_video_count=10,
                channel_view_count=50000, video_title="A title")
    return PredictionInput(**{**base, **overrides})


@pytest.mark.parametrize("category, expected", [
    ("Sports", "Sports"), ("sports", "Sports"), (" Music ", "Music"), ("17", "Sports"), (17, "Sports"),
    ("28", "Science & Technology"), ("29", "Nonprofits & Activism"),
])
def test_supported_category(predictor, category, expected):
    assert predictor.predict(_input(category=category)).category == expected


@pytest.mark.parametrize("category, message", [
    ("Cooking", "unsupported category 'Cooking'"),
    ("None", "unsupported category 'None'"),
    ("", "unsupported category ''"),
    ("999", "unknown YouTube category ID '999'"),
    (None, "must be a category name or YouTube category ID"),
])
def test_unsupported_category(predictor, category, message):
    with pytest.raises(InvalidInputError, match=re.escape(message)) as exc:
        predictor.predict(_input(category=category))
    assert exc.value.errors[0]["field"] == "category"


@pytest.mark.parametrize("country", ["AU", "CA", "GB", "IE", "IN", "NZ", "US", "ZA", "in", " us "])
def test_supported_country(predictor, country):
    assert predictor.predict(_input(country=country)).country == country.strip().upper()


@pytest.mark.parametrize("country", ["SG", "XX", "", None, "India"])
def test_unsupported_country(predictor, country):
    with pytest.raises(InvalidInputError, match="unsupported country") as exc:
        predictor.predict(_input(country=country))
    assert exc.value.errors[0]["field"] == "country"
    assert "AU, CA, GB, IE, IN, NZ, US, ZA" in str(exc.value)


@pytest.mark.parametrize("field, value", [
    ("channel_subscriber_count", -1),
    ("channel_view_count", float("nan")),
    ("video_duration_sec", float("inf")),
    ("channel_video_count", "10"),
    ("channel_video_count", True),
])
def test_invalid_numeric(predictor, field, value):
    with pytest.raises(InvalidInputError, match="must be a finite number >= 0"):
        predictor.predict(_input(**{field: value}))


def test_invalid_text_and_multiple_errors_reported_together(predictor):
    with pytest.raises(InvalidInputError) as exc:
        predictor.predict(_input(video_title=None, country="SG", category="Cooking"))
    assert {e["field"] for e in exc.value.errors} == {"video_title", "country", "category"}
