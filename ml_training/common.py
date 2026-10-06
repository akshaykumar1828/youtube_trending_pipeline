"""Shared paths, constants, database access and metrics for the v2 training experiments.

Nothing here touches the application (backend/, ml/, model/). The database is only read:
every session is opened with default_transaction_read_only=on.
"""

import json
import os
import random
from pathlib import Path

import numpy as np
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent            # ml_training/
REPO = ROOT.parent
CACHE = ROOT / "cache"                            # git-ignored: datasets, embeddings
ARTIFACTS = ROOT / "artifacts"                    # git-ignored: trained model output
RESULTS = ROOT / "results"                        # evaluation results and label thresholds
for d in (CACHE, ARTIFACTS, RESULTS):
    d.mkdir(exist_ok=True)

SEED = 42

# The 8 countries the model supports (Singapore is not in the training data).
COUNTRIES = ("AU", "CA", "GB", "IE", "IN", "NZ", "US", "ZA")
INDIA_BASE_VIEWS = 100_000   # label definition (views threshold for India)


def seed_everything(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


def db_url():
    """Admin credentials from the repo .env, used read-only (raw tables are not readable by the
    application roles)."""
    from sqlalchemy.engine import URL
    cfg = dotenv_values(REPO / ".env")
    return URL.create("postgresql+psycopg2", username=cfg.get("DB_USER") or "postgres",
                      password=cfg["DB_PASSWORD"], host=cfg.get("DB_HOST") or "localhost",
                      port=int(cfg.get("DB_PORT") or 5432), database=cfg["DB_NAME"])


def read_only_engine():
    from sqlalchemy import create_engine
    return create_engine(db_url(), connect_args={
        "options": "-c default_transaction_read_only=on -c statement_timeout=0",
        "application_name": "yt_ml_training"})


# ------------------------------------------------------------------------------------------
# Metrics
# ------------------------------------------------------------------------------------------
def expected_calibration_error(y, p, bins=10):
    y, p = np.asarray(y), np.asarray(p)
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.any():
            ece += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(ece)


def metrics(y, p):
    from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
    y, p = np.asarray(y), np.clip(np.asarray(p, dtype=float), 1e-7, 1 - 1e-7)
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "log_loss": float(log_loss(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "ece": expected_calibration_error(y, p),
        "n": int(len(y)),
        "positive_rate": float(np.mean(y)),
    }


def save_result(name, payload):
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=float))
    return path
