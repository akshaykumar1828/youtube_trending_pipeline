"""Compare the app's model (v3) with the previous model (v1) on the SAME rows and labels.

v1 was removed from the working tree; its files are read straight from git history (commit
6ebf969, read-only, into a temporary folder) and scored the way the old app scored them.

    .venv\\Scripts\\python compare_v1.py

Rows compared:
  * the time-split test rows (cache/test_predictions_v3.parquet from train_v3.py);
  * a saved live fetch (cache/live_raw_*.json from live_test.py), re-labelled with the
    current thresholds (results/label_thresholds.json) and scored by the app's v3 code path.
Rows whose category v1 did not support are excluded for both models.
"""

import throttle  # noqa: F401  (first)

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from common import CACHE, REPO, RESULTS, save_result

V1_COMMIT = "6ebf969"
V1_FILES = ["clip_values", "meta_lr", "ohe", "psych_lr", "psych_scaler", "rf_calibrated", "text_lr", "text_scaler"]


def load_v1(tmp: Path):
    for name in V1_FILES:
        blob = subprocess.run(["git", "show", f"{V1_COMMIT}:model/{name}.pkl"], cwd=REPO, capture_output=True, check=True).stdout
        (tmp / f"{name}.pkl").write_bytes(blob)
    src = subprocess.run(["git", "show", f"{V1_COMMIT}:ml/features.py"], cwd=REPO, capture_output=True, check=True).stdout
    (tmp / "v1_features.py").write_bytes(src)
    spec = importlib.util.spec_from_file_location("v1_features", tmp / "v1_features.py")
    feats = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(feats)
    return {n: joblib.load(tmp / f"{n}.pkl") for n in V1_FILES}, feats


def v1_predict(arts, feats, rows, emb):
    text = arts["text_lr"].predict_proba(arts["text_scaler"].transform(emb))[:, 1]
    num = np.vstack([feats.numeric_features(d, s, v, cv, arts["clip_values"]["vpv_clip"], arts["clip_values"]["spv_clip"])[0]
                     for d, s, v, cv in zip(rows["video_duration_sec"], rows["channel_subscriber_count"],
                                            rows["channel_video_count"], rows["channel_view_count"])])
    cat = arts["ohe"].transform(rows[["video_category_id", "country"]].astype(str))
    rf = arts["rf_calibrated"].predict_proba(np.hstack([cat, num]))[:, 1]
    psych = np.vstack([feats.psych_features(t)[0] for t in rows["video_title"]])
    ps = arts["psych_lr"].predict_proba(arts["psych_scaler"].transform(psych))[:, 1]
    return arts["meta_lr"].predict_proba(np.column_stack([text, rf, ps]))[:, 1]


def scores(y, p):
    return {"roc_auc": round(float(roc_auc_score(y, p)), 4),
            "accuracy_at_0.5": round(float(((p >= 0.5) == y).mean()), 4), "mean_predicted": round(float(p.mean()), 4)}


def main():
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        arts, feats = load_v1(Path(tmp))
    v1_categories = set(arts["ohe"].categories_[0]) - {"None"}

    # 1. time-split test rows
    import train_v3
    df, emb = train_v3.load_rows()
    test = (df["time_split"] == "test").values
    rows, e = df[test].reset_index(drop=True), emb[test]
    v3 = pd.read_parquet(CACHE / "test_predictions_v3.parquet")
    assert (v3["video_id"].values == rows["video_id"].values).all()
    keep = rows["video_category_id"].isin(v1_categories).values
    y = rows["label"].values[keep]
    p1 = v1_predict(arts, feats, rows[keep], e[keep])
    p3 = v3["v3"].values[keep]
    out["time_test"] = {"rows": int(keep.sum()), "positive_rate": round(float(y.mean()), 4),
                        "v1": scores(y, p1), "v3": scores(y, p3),
                        "by_country": {c: {"v1": round(float(roc_auc_score(y[g], p1[g])), 4),
                                           "v3": round(float(roc_auc_score(y[g], p3[g])), 4), "n": int(len(g))}
                                       for c, g in pd.Series(rows["country"].values[keep]).groupby(rows["country"].values[keep]).indices.items()
                                       if len(set(y[g])) == 2}}
    print(json.dumps(out["time_test"], indent=1))

    # 2. saved live fetch, re-labelled with the current thresholds
    live_files = sorted(CACHE.glob("live_raw_*.json"))
    if live_files:
        sys.path.insert(0, str(REPO))
        from ml import PredictionInput, TrendingPredictor
        live = pd.read_json(live_files[-1])
        stamp = live_files[-1].stem.removeprefix("live_raw_")
        th = json.loads((RESULTS / "label_thresholds.json").read_text())
        live["actual"] = ((live["video_view_count"] >= live["country"].map(th["view_threshold"]))
                          & (live["video_like_count"] >= live["country"].map(th["like_threshold"]))
                          & (live["video_comment_count"] >= live["country"].map(th["comment_threshold"]))).astype(int)
        e_live = np.load(CACHE / f"emb_live_{stamp.replace('-', '')}.npy")   # same fetch, same row order
        keep = live["video_category_id"].isin(v1_categories).values
        lv = live[keep].reset_index(drop=True)
        p1 = v1_predict(arts, feats, lv, e_live[keep])
        predictor = TrendingPredictor(device="cpu")
        p3 = np.array([predictor.predict(PredictionInput(
            category=r.video_category_id, country=r.country, video_duration_sec=r.video_duration_sec,
            channel_subscriber_count=r.channel_subscriber_count, channel_video_count=r.channel_video_count,
            channel_view_count=r.channel_view_count, video_title=r.video_title,
            video_description=r.video_description, video_tags=r.video_tags,
            channel_title=r.channel_title)).final_probability for r in lv.itertuples()])
        y = lv["actual"].values
        recent = (lv["hours_since_published"] <= 48).values
        out["live"] = {"fetched": stamp, "videos": int(len(lv)), "positive_rate": round(float(y.mean()), 4),
                       "v1": scores(y, p1), "v3": scores(y, p3),
                       "published_last_48h": {"videos": int(recent.sum()), "v1": scores(y[recent], p1[recent]),
                                              "v3": scores(y[recent], p3[recent])},
                       "by_country": {c: {"v1": round(float(roc_auc_score(y[g], p1[g])), 4),
                                          "v3": round(float(roc_auc_score(y[g], p3[g])), 4),
                                          "actual_rate": round(float(y[g].mean()), 2)}
                                      for c, g in lv.groupby("country").indices.items() if len(set(y[g])) == 2}}
        lv.assign(v1_predicted=p1, v3_predicted=p3)[
            ["country", "rank", "video_id", "video_title", "channel_title", "video_category_id", "hours_since_published",
             "video_view_count", "video_like_count", "video_comment_count", "actual", "v3_predicted", "v1_predicted"]
        ].to_csv(RESULTS / f"live_test_{stamp}_final.csv", index=False, encoding="utf-8-sig")
        print(json.dumps(out["live"], indent=1))
    save_result("compare_v1_v3", out)


if __name__ == "__main__":
    main()
