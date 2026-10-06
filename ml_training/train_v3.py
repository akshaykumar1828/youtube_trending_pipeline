"""Train and evaluate the app's model (v3). Features come from the app's own ml/features.py,
so training and serving use one definition.

    .venv\\Scripts\\python train_v3.py              # time-split evaluation + artifacts/trending_model_v3.joblib
    .venv\\Scripts\\python train_v3.py --all-data   # retrain on all rows (no evaluation possible)

Data: one row per (video, country) first trending appearance in the 8 supported countries.
Label (the v1 rule): high performer in a country when views >= 100,000 x (country median views /
India median views) AND likes >= country median AND comments >= country median, where the medians
are taken over all first appearances IN THAT COUNTRY (these rows). The thresholds are saved to
results/label_thresholds.json. The video-level time split comes from the per-video dataset
(data.py), so all country rows of a video share one split.
Model: two gradient-boosting models on the same features, one without the channel numbers
(ml.features.CHANNEL_NUMBER_FEATURES); the prediction is their logit blend (ml.features.blend,
weight CONFIG["blend_weight"]), chosen in numeric_reliance.py to limit reliance on channel numbers.
Copy the produced artifact to model/trending_model_v3.joblib and regenerate the reference
predictions (make_reference.py) to deploy it.
"""

import throttle  # noqa: F401  (first: caps CPU threads)

import json
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import ARTIFACTS, CACHE, INDIA_BASE_VIEWS, REPO, RESULTS, SEED, metrics, save_result, seed_everything
from data import _load_raw, build_dataset
from embed import embeddings

sys.path.insert(0, str(REPO))
from ml.features import CHANNEL_NUMBER_FEATURES, blend, model_table, texts  # noqa: E402  (the app's feature code)

# Chosen on the validation set (see REPORT.md); not re-tuned here.
CONFIG = {
    "text_C": 0.03,
    "pca_dims": 32,
    "recency_tau_days": 90,
    # weight of the model WITHOUT channel numbers in the final blend (chosen with
    # numeric_reliance.py: AUC -0.004, reliance on channel numbers -64 %)
    "blend_weight": 0.5,
    "gbm": dict(learning_rate=0.03, max_leaf_nodes=63, min_samples_leaf=100, l2_regularization=0.0,
                max_iter=4000, early_stopping=True, validation_fraction=0.1, n_iter_no_change=50,
                random_state=SEED, categorical_features="from_dtype"),
}
ROWS = CACHE / "rows_video_country.parquet"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------------------------------
# data
# ------------------------------------------------------------------------------------------
def label_thresholds(rows):
    """Per-country medians over first appearances in that country; saved for the live check."""
    med = rows.groupby("country")["video_view_count"].median()
    view_th = INDIA_BASE_VIEWS * med / med.loc["IN"]
    like_th = rows.groupby("country")["video_like_count"].median()
    comment_th = rows.groupby("country")["video_comment_count"].median()
    (RESULTS / "label_thresholds.json").write_text(json.dumps({
        "description": "Label rule thresholds: medians over each country's first trending appearances "
                       f"(per video and country), {rows['video_trending_date'].min().date()} to "
                       f"{rows['video_trending_date'].max().date()}. High performer = views >= "
                       "view_threshold AND likes >= like_threshold AND comments >= comment_threshold.",
        "view_threshold": view_th.round(4).to_dict(), "like_threshold": like_th.to_dict(),
        "comment_threshold": comment_th.to_dict()}, indent=2))
    return view_th, like_th, comment_th


def split_ends():
    """Last first-appearance date of the training and validation videos. Rows dated after it
    (a video's later appearances in other countries) are not used for fitting that stage."""
    per_video = build_dataset()
    return per_video.groupby("time_split")["video_trending_date"].max().to_dict()


def load_rows():
    per_video = build_dataset()
    if ROWS.exists():
        df = pd.read_parquet(ROWS)
    else:
        raw = _load_raw()
        raw["video_trending_date"] = pd.to_datetime(raw["video_trending_date"]).dt.normalize()
        df = (raw.sort_values(["video_trending_date", "country", "video_id"], kind="mergesort")
                 .drop_duplicates(["video_id", "country"], keep="first").reset_index(drop=True))
        # Some 2026 snapshots have no statistics at all (YouTube returned none: views NULL);
        # their label is unknown, so those (video, country) rows are left out.
        df = df[df["video_view_count"].notna()].reset_index(drop=True)
        view_th, like_th, comment_th = label_thresholds(df)
        df["label"] = ((df["video_view_count"] >= df["country"].map(view_th))
                       & (df["video_like_count"] >= df["country"].map(like_th))
                       & (df["video_comment_count"] >= df["country"].map(comment_th))).astype(np.int8)
        for col in ("channel_title", "video_title", "video_description", "video_tags"):
            df[col] = df[col].fillna("").astype(str)
        df["video_category_id"] = df["video_category_id"].fillna("").astype(str).str.strip().replace("", "None")
        for col in ("video_duration_sec", "channel_view_count", "channel_subscriber_count", "channel_video_count"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)
        vid = per_video[["video_id", "time_split"]].reset_index().rename(columns={"index": "video_row"})
        df = df.merge(vid, on="video_id", how="left", validate="many_to_one")
        df.to_parquet(ROWS, index=False)
    # Text depends only on the video, so it is embedded once per video.
    emb = embeddings("served", texts(per_video))[df["video_row"].values]
    return df, emb


# ------------------------------------------------------------------------------------------
# model
# ------------------------------------------------------------------------------------------
def text_model():
    return make_pipeline(StandardScaler(), LogisticRegression(C=CONFIG["text_C"], max_iter=3000))


def clip_values(df):
    vids = df["channel_video_count"].clip(lower=1)
    return (float((df["channel_view_count"] / vids).quantile(0.995)),
            float((df["channel_subscriber_count"] / vids).quantile(0.995)))


def fit(df, emb, mask):
    rows, e, y = df[mask], emb[mask], df["label"].values[mask]
    # out-of-fold text score, grouped by video (a video never scores itself)
    oof = np.zeros(len(y))
    for tr, va in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED).split(e, y, rows["video_id"]):
        oof[va] = text_model().fit(e[tr], y[tr]).predict_proba(e[va])[:, 1]
    text_full = text_model().fit(e, y)
    pca = PCA(n_components=CONFIG["pca_dims"], random_state=SEED).fit(e)
    clips = clip_values(rows)
    X = model_table(rows, *clips, oof, pca.transform(e))
    age = (rows["video_trending_date"].max() - rows["video_trending_date"]).dt.days.values
    weight = np.exp(-age / CONFIG["recency_tau_days"])
    gbm = HistGradientBoostingClassifier(**CONFIG["gbm"]).fit(X, y, sample_weight=weight)
    no_channel = [c for c in X.columns if c not in CHANNEL_NUMBER_FEATURES]
    gbm_no_channel = HistGradientBoostingClassifier(**CONFIG["gbm"]).fit(X[no_channel], y, sample_weight=weight)
    return {"config": CONFIG, "clips": clips, "text_model": text_full, "pca": pca, "gbm": gbm,
            "gbm_no_channel": gbm_no_channel, "columns_no_channel": no_channel,
            "blend_weight": CONFIG["blend_weight"], "columns": list(X.columns),
            "categories": {c: list(X[c].cat.categories) for c in ("video_category_id", "country")},
            "trained_until": str(rows["video_trending_date"].max().date()), "n_train": int(mask.sum())}


def predict(model, df, emb):
    X = model_table(df, *model["clips"], model["text_model"].predict_proba(emb)[:, 1], model["pca"].transform(emb))
    for col, cats in model["categories"].items():
        X[col] = pd.Categorical(X[col].astype(str), categories=cats)
    return blend(model["gbm"].predict_proba(X[model["columns"]])[:, 1],
                 model["gbm_no_channel"].predict_proba(X[model["columns_no_channel"]])[:, 1], model["blend_weight"])


# ------------------------------------------------------------------------------------------
def main():
    seed_everything()
    log(f"limits: {throttle.THREADS} CPU threads")
    df, emb = load_rows()
    log(f"{len(df)} (video, country) rows from {df['video_id'].nunique()} videos")
    if "--all-data" in sys.argv:
        model = fit(df, emb, np.ones(len(df), bool))
        joblib.dump(model, ARTIFACTS / "trending_model_v3_all_data.joblib", compress=3)
        log(f"saved model trained on all {len(df)} rows (until {model['trained_until']})")
        return
    log(f"positive rate: {df['label'].mean():.3f}; by country {df.groupby('country')['label'].mean().round(3).to_dict()}")
    # validation: train on the training period only, score the validation period
    ends = split_ends()
    log(f"split ends: train {ends['train'].date()}, validation {ends['val'].date()}, test {ends['test'].date()}")
    tr = ((df["time_split"] == "train") & (df["video_trending_date"] <= ends["train"])).values
    va = (df["time_split"] == "val").values
    val_model = fit(df, emb, tr)
    val = metrics(df["label"].values[va], predict(val_model, df[va], emb[va]))
    log(f"validation ROC-AUC {val['roc_auc']:.4f}")
    throttle.pause(throttle.STAGE_PAUSE, "cool-down")

    fit_mask = (df["time_split"].isin(["train", "val"]) & (df["video_trending_date"] <= ends["val"])).values
    test = (df["time_split"] == "test").values
    model = fit(df, emb, fit_mask)
    p, y = predict(model, df[test], emb[test]), df["label"].values[test]
    by_country = {c: round(metrics(y[g], p[g])["roc_auc"], 4)
                  for c, g in pd.Series(df.loc[test, "country"].values).groupby(df.loc[test, "country"].values).indices.items()
                  if len(set(y[g])) == 2}
    result = {"validation": val, "test": metrics(y, p), "by_country": by_country,
              "trained_until": model["trained_until"], "n_train": model["n_train"]}
    pd.DataFrame({"video_id": df.loc[test, "video_id"].values, "country": df.loc[test, "country"].values,
                  "label": y, "v3": p}).to_parquet(CACHE / "test_predictions_v3.parquet", index=False)
    save_result("train_v3", result)
    joblib.dump(model, ARTIFACTS / "trending_model_v3.joblib", compress=3)
    log(f"time-split test ROC-AUC {result['test']['roc_auc']:.4f}; by country {by_country}")
    log(json.dumps({k: round(v, 4) for k, v in result["test"].items() if isinstance(v, float)}))


if __name__ == "__main__":
    main()
