"""Prediction API tests with the real frozen model (loaded once for this module).

The API must return exactly what ml.TrendingPredictor returns (the model's random forest
varies by ~1e-16 between calls, so float comparisons allow 1e-12) and match the Phase 1
reference outputs of the legacy predictor at 4 decimals."""

import json
import subprocess
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from api_support import BACKEND, PREDICTION_BODY, REPO_ROOT, make_settings, sign_in_as
from app.main import create_app

REFERENCE = json.loads((REPO_ROOT / "tests" / "fixtures" / "reference_predictions.json").read_text(encoding="utf-8"))
TOL = 1e-12


@pytest.fixture(scope="module")
def ml_app():
    app = create_app(make_settings(ml_enabled=True, ml_preload=True))
    sign_in_as(app)  # MEMBER: has MAKE_PREDICTION
    with TestClient(app) as client:  # lifespan preloads the model
        yield app, client


@pytest.fixture(scope="module")
def client(ml_app):
    return ml_app[1]


@pytest.fixture(scope="module")
def predictor(ml_app):
    return ml_app[0].state.prediction_service._predictor


def body_from_legacy(legacy):
    return {
        "title": legacy["video_title"], "description": legacy["video_description"],
        "tags": legacy["video_tags"].split(",") if legacy["video_tags"] else [],
        "channel_title": legacy["channel_title"], "category": legacy["video_category_id"],
        "country": legacy["country"], "duration_sec": legacy["video_duration_sec"],
        "channel_subscriber_count": legacy["channel_subscriber_count"],
        "channel_video_count": legacy["channel_video_count"],
        "channel_view_count": legacy["channel_view_count"],
    }


def test_model_loaded_at_startup(ml_app):
    health = ml_app[0].state.prediction_service.health()
    assert health["status"] == "loaded" and health["load_seconds"] > 0 and len(health["version"]) == 12


@pytest.mark.parametrize("case", REFERENCE["cases"], ids=[c["name"] for c in REFERENCE["cases"]])
def test_api_equals_direct_predictor_and_legacy_reference(client, predictor, case):
    from ml import PredictionInput

    r = client.post("/api/v1/predictions", json=body_from_legacy(case["input"]))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    direct = predictor.predict(PredictionInput.from_legacy_dict(case["input"]))

    pairs = [(data["high_performance_probability"], direct.final_probability),
             (data["components"]["text"], direct.text_score),
             (data["components"]["channel_and_numeric"], direct.numeric_score),
             (data["components"]["psychology"], direct.psychology_score)]
    for api_value, direct_value in pairs:
        assert abs(api_value - direct_value) <= TOL
    assert data["inputs_used"] == {"category": direct.category, "country": direct.country}

    expected = case["expected"]  # legacy predictor.py output (4 decimals)
    assert round(data["high_performance_probability"], 4) == expected["final_probability"]
    assert round(data["components"]["text"], 4) == expected["text_score"]
    assert round(data["components"]["channel_and_numeric"], 4) == expected["numeric_score"]
    assert round(data["components"]["psychology"], 4) == expected["psychology_score"]


def test_category_id_is_converted(client):
    by_id = client.post("/api/v1/predictions", json={**PREDICTION_BODY, "category": 17}).json()["data"]
    by_name = client.post("/api/v1/predictions", json={**PREDICTION_BODY, "category": "sports"}).json()["data"]
    assert by_id["inputs_used"]["category"] == by_name["inputs_used"]["category"] == "Sports"
    assert abs(by_id["high_performance_probability"] - by_name["high_performance_probability"]) <= TOL


def test_unsupported_inputs_are_422_from_model_layer(client):
    r = client.post("/api/v1/predictions", json={**PREDICTION_BODY, "country": "SG", "category": "Cooking"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_prediction_input"
    assert {d["field"] for d in err["details"]} == {"country", "category"}
    assert "AU, CA, GB, IE, IN, NZ, US, ZA" in r.text


def test_model_info(client, predictor):
    r = client.get("/api/v1/predictions/model-info")
    info = r.json()["data"]
    assert info["output"] == "high_performance_probability"
    assert info["supported_countries"] == list(predictor.supported_countries)
    assert info["supported_categories"] == list(predictor.supported_categories) and len(info["supported_categories"]) == 14
    assert "already on a YouTube trending list" in info["label_definition"]
    assert "does not estimate whether an arbitrary video will reach a trending list" in info["not_a_prediction_of"]
    assert any("Singapore" in lim for lim in info["limitations"])
    assert any("fixed at 0" in lim for lim in info["limitations"])


def test_no_internal_artifacts_exposed(client):
    for r in (client.post("/api/v1/predictions", json=PREDICTION_BODY), client.get("/api/v1/predictions/model-info")):
        for leak in (".pkl", "model/", "model\\\\", "joblib", "ohe", "clip_values", str(REPO_ROOT).replace("\\", "/")):
            assert leak not in r.text, leak


def test_concurrent_requests_are_serialized_and_consistent(client):
    results, errors = [], []

    def call():
        try:
            r = client.post("/api/v1/predictions", json=PREDICTION_BODY)
            results.append(r.json()["data"]["high_performance_probability"])
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=call) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(results) == 4
    assert max(results) - min(results) <= TOL


def test_prediction_path_never_imports_streamlit_or_legacy_predictor():
    script = f"""
import sys
sys.path[:0] = [r"{BACKEND}", r"{REPO_ROOT}", r"{BACKEND / 'tests' / 'api'}"]
from fastapi.testclient import TestClient
from api_support import make_settings, sign_in_as
from app.main import create_app
body = {PREDICTION_BODY!r}
app = create_app(make_settings(ml_enabled=True, ml_preload=True))
sign_in_as(app)
with TestClient(app) as c:
    assert c.post("/api/v1/predictions", json=body).status_code == 200
print("streamlit=" + str("streamlit" in sys.modules), "predictor=" + str("predictor" in sys.modules))
"""
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=600, cwd=REPO_ROOT)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "streamlit=False predictor=False" in out.stdout
