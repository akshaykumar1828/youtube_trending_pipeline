"""How much should the model lean on channel numbers (subscribers, channel views, video count)?

Variants (all keep duration, title/description signals, category, country and the LaBSE text):
  A_full         the current v3 features: all 9 channel-number features
  B_raw3         only the three raw channel sizes (log subscribers, log channel views, log video count)
  B_subs         only log subscribers
  D_no_channel   no channel numbers at all
  C_blend_<w>    probability blend (logit average) of A_full and D_no_channel, weight w on D

Every variant is fitted on the training period and scored on the validation period exactly like
train_v3.py (same text model, PCA and recency weights). For each one we report:
  * validation ROC-AUC / PR-AUC / log loss;
  * reliance: AUC lost when the channel numbers are shuffled between videos (0 = ignores them);
  * robustness: how far predictions move (percentage points) when channel inputs are wrong:
      wrong_scale  channel views / 1000 and subscribers x 10 (a units mistake),
      subs_x10     subscribers x 10 only.

    .venv\\Scripts\\python numeric_reliance.py      -> results/numeric_reliance.json
"""

import throttle  # noqa: F401  (first: caps CPU threads)

import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.decomposition import PCA
from sklearn.model_selection import StratifiedGroupKFold

from common import REPO, SEED, metrics, save_result, seed_everything
from train_v3 import CONFIG, clip_values, load_rows, log, split_ends, text_model

sys.path.insert(0, str(REPO))
from ml.features import channel_features, logit, model_table  # noqa: E402

CHANNEL_INPUTS = ["channel_subscriber_count", "channel_view_count", "channel_video_count"]
CHANNEL_FEATURES = ["log_subscriber_count", "log_view_count", "channel_authority", "views_per_video_log",
                    "subs_per_video_log", "legacy_channel", "video_volume_bucket", "log_video_count",
                    "log_views_per_sub"]
KEEP = {
    "A_full": CHANNEL_FEATURES,
    "B_raw3": ["log_subscriber_count", "log_view_count", "log_video_count"],
    "B_subs": ["log_subscriber_count"],
    "D_no_channel": [],
}
BLEND_WEIGHTS = (0.3, 0.5, 0.7)


def perturb(rows, kind, rng):
    out = rows.copy()
    if kind == "wrong_scale":
        out["channel_view_count"] = out["channel_view_count"] / 1000
        out["channel_subscriber_count"] = out["channel_subscriber_count"] * 10
    elif kind == "subs_x10":
        out["channel_subscriber_count"] = out["channel_subscriber_count"] * 10
    elif kind == "shuffle":   # channel numbers of a random other video (jointly, so they stay coherent)
        idx = rng.permutation(len(out))
        out[CHANNEL_INPUTS] = out[CHANNEL_INPUTS].values[idx]
    return out


def with_channel(table, rows, clips):
    """`table` with its channel/duration columns recomputed from (possibly perturbed) rows."""
    out = table.copy()
    ch = channel_features(rows, *clips).reset_index(drop=True)
    out[ch.columns] = ch
    return out


def main():
    seed_everything()
    rng = np.random.default_rng(SEED)
    df, emb = load_rows()
    ends = split_ends()
    tr = ((df["time_split"] == "train") & (df["video_trending_date"] <= ends["train"])).values
    va = (df["time_split"] == "val").values
    rtr, rva = df[tr].reset_index(drop=True), df[va].reset_index(drop=True)
    etr, eva = emb[tr], emb[va]
    ytr, yva = rtr["label"].values, rva["label"].values
    log(f"train {len(rtr)} rows (until {ends['train'].date()}), validation {len(rva)} rows")

    # shared text pieces, exactly as train_v3.fit
    oof = np.zeros(len(ytr))
    for a, b in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED).split(etr, ytr, rtr["video_id"]):
        oof[b] = text_model().fit(etr[a], ytr[a]).predict_proba(etr[b])[:, 1]
    text_full = text_model().fit(etr, ytr)
    pca = PCA(n_components=CONFIG["pca_dims"], random_state=SEED).fit(etr)
    clips = clip_values(rtr)
    Xtr = model_table(rtr, *clips, oof, pca.transform(etr))
    Xva = model_table(rva, *clips, text_full.predict_proba(eva)[:, 1], pca.transform(eva))
    for col in ("video_category_id", "country"):
        Xva[col] = pd.Categorical(Xva[col].astype(str), categories=Xtr[col].cat.categories)
    scenarios = {"base": Xva}
    for kind in ("wrong_scale", "subs_x10", "shuffle"):
        scenarios[kind] = with_channel(Xva, perturb(rva, kind, rng), clips)
    log("text model and feature tables ready")
    throttle.pause(throttle.STAGE_PAUSE / 2, "cool-down")

    age = (rtr["video_trending_date"].max() - rtr["video_trending_date"]).dt.days.values
    weight = np.exp(-age / CONFIG["recency_tau_days"])
    preds = {}
    for name, keep in KEEP.items():
        cols = [c for c in Xtr.columns if c not in CHANNEL_FEATURES or c in keep]
        gbm = HistGradientBoostingClassifier(**CONFIG["gbm"]).fit(Xtr[cols], ytr, sample_weight=weight)
        preds[name] = {k: gbm.predict_proba(X[cols])[:, 1] for k, X in scenarios.items()}
        log(f"{name}: {len(cols)} features, {gbm.n_iter_} trees, AUC {metrics(yva, preds[name]['base'])['roc_auc']:.4f}")
        throttle.pause(throttle.STAGE_PAUSE / 3, "cool-down")
    for w in BLEND_WEIGHTS:
        preds[f"C_blend_{w}"] = {k: 1 / (1 + np.exp(-((1 - w) * logit(preds["A_full"][k]) + w * logit(preds["D_no_channel"][k]))))
                                 for k in scenarios}

    result = {"train_until": str(ends["train"].date()), "n_train": len(rtr), "n_val": len(rva), "variants": {}}
    for name, p in preds.items():
        base = metrics(yva, p["base"])
        r = {"roc_auc": base["roc_auc"], "pr_auc": base["pr_auc"], "log_loss": base["log_loss"], "ece": base["ece"],
             "reliance_auc_drop_when_shuffled": base["roc_auc"] - metrics(yva, p["shuffle"])["roc_auc"]}
        for kind in ("wrong_scale", "subs_x10"):
            d = np.abs(p[kind] - p["base"]) * 100
            r[f"{kind}_mean_change_pp"] = float(d.mean())
            r[f"{kind}_p90_change_pp"] = float(np.percentile(d, 90))
            r[f"{kind}_auc"] = metrics(yva, p[kind])["roc_auc"]
        result["variants"][name] = r
    save_result("numeric_reliance", result)
    table = pd.DataFrame(result["variants"]).T
    print(table[["roc_auc", "pr_auc", "log_loss", "reliance_auc_drop_when_shuffled", "wrong_scale_mean_change_pp",
                 "wrong_scale_p90_change_pp", "subs_x10_mean_change_pp", "wrong_scale_auc"]].round(4).to_string())


if __name__ == "__main__":
    main()
