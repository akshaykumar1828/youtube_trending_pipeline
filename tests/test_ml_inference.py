"""Tests for the standalone ML inference layer (ml/).

The model is frozen: these tests prove that ml/ reproduces the legacy
predictor.py exactly, never modifies the artifacts, and does not need Streamlit.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
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


# ---------------------------------------------------
# NO STREAMLIT (runs first, in a fresh interpreter, before fixtures load models)
# ---------------------------------------------------
def test_inference_runs_without_streamlit():
    code = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from ml import TrendingPredictor, PredictionInput\n"
        "p = TrendingPredictor()\n"
        "r = p.predict(PredictionInput(category='Sports', country='IN', video_duration_sec=140,"
        " channel_subscriber_count=1000, channel_video_count=10, channel_view_count=50000, video_title='t'))\n"
        "assert 0.0 <= r.final_probability <= 1.0\n"
        "print('streamlit_loaded=' + str('streamlit' in sys.modules))\n" % ROOT
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "streamlit_loaded=False" in out.stdout


def test_ml_package_has_no_streamlit_import():
    for path in (ROOT / "ml").glob("*.py"):
        assert "streamlit" not in path.read_text(encoding="utf-8"), path.name


# ---------------------------------------------------
# ARTIFACTS ARE FROZEN
# ---------------------------------------------------
def test_artifacts_unchanged():
    model_dir = ROOT / ARTIFACT_HASHES["directory"]
    actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(model_dir.iterdir())}
    assert actual == ARTIFACT_HASHES["files"]


def test_ml_code_never_writes_or_fits():
    pattern = re.compile(r"\b(dump|fit|fit_transform|partial_fit)\s*\(")
    for path in (ROOT / "ml").glob("*.py"):
        assert not pattern.search(path.read_text(encoding="utf-8")), path.name


# ---------------------------------------------------
# FIXTURES
# ---------------------------------------------------
@pytest.fixture(scope="session")
def predictor():
    return TrendingPredictor()


@pytest.fixture(scope="session")
def legacy():
    import predictor as legacy_predictor  # unmodified Streamlit-coupled module (bare mode)
    return legacy_predictor


# ---------------------------------------------------
# LOADING + DIMENSIONS
# ---------------------------------------------------
def test_artifacts_and_labse_load(predictor):
    assert predictor.embedder.get_sentence_embedding_dimension() == 768
    assert predictor.text_scaler.n_features_in_ == 768
    assert predictor.text_lr.n_features_in_ == 768
    assert predictor.rf_calibrated.n_features_in_ == 31
    assert predictor.psych_scaler.n_features_in_ == 8
    assert predictor.psych_lr.n_features_in_ == 8
    assert predictor.meta_lr.n_features_in_ == 3


def test_feature_dimensions_and_order_match_model(predictor):
    num = features.numeric_features(140, 1000, 10, 50000, predictor.vpv_clip, predictor.spv_clip)
    cat = predictor.ohe.transform(features.categorical_frame("Sports", "IN"))
    psych = features.psych_features("title")

    assert num.shape == (1, len(features.NUMERIC_FEATURES)) == (1, 8)
    assert cat.shape == (1, 23)
    assert cat.shape[1] + num.shape[1] == predictor.rf_calibrated.n_features_in_
    assert psych.shape == (1, 8)
    assert tuple(predictor.psych_scaler.feature_names_in_) == features.PSYCH_FEATURES
    assert tuple(predictor.ohe.feature_names_in_) == ("video_category_id", "country")


def test_supported_values_come_from_encoder(predictor):
    assert predictor.supported_countries == ("AU", "CA", "GB", "IE", "IN", "NZ", "US", "ZA")
    assert "None" not in predictor.supported_categories
    assert len(predictor.supported_categories) == 14


# ---------------------------------------------------
# PARITY WITH THE LEGACY PREDICTOR
# ---------------------------------------------------
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_matches_reference_predictions(predictor, case):
    result = predictor.predict(PredictionInput.from_legacy_dict(case["input"]))
    assert result.to_legacy_dict() == case["expected"]


class _Recorder:
    """Wraps a model and records every array passed to predict_proba."""

    def __init__(self, model):
        self.model = model
        self.inputs = []

    def predict_proba(self, X):
        self.inputs.append(np.array(X, copy=True))
        return self.model.predict_proba(X)


def _record(monkeypatch, owner):
    recorders = {}
    for name in ("text_lr", "rf_calibrated", "psych_lr", "meta_lr"):
        recorders[name] = _Recorder(getattr(owner, name))
        monkeypatch.setattr(owner, name, recorders[name])
    return recorders


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_model_inputs_identical_to_legacy(predictor, legacy, monkeypatch, case):
    legacy_rec = _record(monkeypatch, legacy)
    new_rec = _record(monkeypatch, predictor)

    legacy.predict_trending(case["input"])
    predictor.predict(PredictionInput.from_legacy_dict(case["input"]))

    # Embedding, RF and psychology inputs must be bit-identical.
    for name in ("text_lr", "rf_calibrated", "psych_lr"):
        (old,), (new,) = legacy_rec[name].inputs, new_rec[name].inputs
        assert old.shape == new.shape, name
        assert np.array_equal(old, new), name

    # Meta input = [text_prob, rf_prob, psych_prob]. The frozen RandomForest uses
    # n_jobs=-1, so its threaded tree summation varies by ~1e-16 between calls
    # even in the legacy predictor; only the rf_prob column gets a tolerance.
    (old,), (new,) = legacy_rec["meta_lr"].inputs, new_rec["meta_lr"].inputs
    assert old.shape == new.shape == (1, 3)
    assert old[0, 0] == new[0, 0] and old[0, 2] == new[0, 2]
    assert abs(old[0, 1] - new[0, 1]) <= 1e-12


def test_intentional_difference_numeric_category_id(predictor, legacy):
    """Legacy silently drops ID '17'; the input adapter maps it to 'Sports'."""
    case = REFERENCE["intentional_difference_cases"][0]
    legacy_out = legacy.predict_trending(case["input"])
    assert legacy_out == case["legacy_output"]

    new = predictor.predict(PredictionInput.from_legacy_dict(case["input"]))
    as_name = legacy.predict_trending({**case["input"], "video_category_id": "Sports"})

    assert new.category == "Sports"
    assert new.to_legacy_dict() == as_name
    assert new.to_legacy_dict() != legacy_out


# ---------------------------------------------------
# PSYCHOLOGY FEATURES (frozen legacy behaviour, explicit constants)
# ---------------------------------------------------
def test_psychology_features_reproduce_legacy_constants():
    vec = features.psych_features("BREAKING viral official emotional news 2025?!")[0]
    as_dict = dict(zip(features.PSYCH_FEATURES, vec))
    for name in ("has_urgency", "has_hype", "has_official_words", "has_emotion",
                 "title_description_overlap_ratio"):
        assert as_dict[name] == 0, name
    assert as_dict["has_number_in_title"] == 1
    assert as_dict["has_question_mark"] == 1
    assert as_dict["has_exclamation"] == 1


def test_result_exposes_features(predictor):
    case = CASES[0]
    result = predictor.predict(PredictionInput.from_legacy_dict(case["input"]))
    assert list(result.features["numeric"]) == list(features.NUMERIC_FEATURES)
    assert list(result.features["psychology"]) == list(features.PSYCH_FEATURES)
    assert result.country == "IN" and result.category == "Sports"


# ---------------------------------------------------
# VALIDATION
# ---------------------------------------------------
def _input(**overrides):
    base = dict(category="Sports", country="IN", video_duration_sec=140,
                channel_subscriber_count=1000, channel_video_count=10,
                channel_view_count=50000, video_title="A title")
    return PredictionInput(**{**base, **overrides})


@pytest.mark.parametrize("category, expected", [
    ("Sports", "Sports"),
    ("sports", "Sports"),
    (" Music ", "Music"),
    ("17", "Sports"),
    (17, "Sports"),
    ("28", "Science & Technology"),
])
def test_supported_category(predictor, category, expected):
    assert predictor.predict(_input(category=category)).category == expected


@pytest.mark.parametrize("category, message", [
    ("Cooking", "unsupported category 'Cooking'"),
    ("None", "unsupported category 'None'"),
    ("", "unsupported category ''"),
    ("29", "(Nonprofits & Activism) is not supported"),
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
