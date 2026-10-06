"""Live check of the app's model on TODAY's YouTube trending videos.

    python live_test.py        (any Python with the app's requirements; uses the GPU if available)

* Data comes straight from the YouTube Data API v3 (videos.list chart=mostPopular, top 50 per
  country for the 8 supported countries) - not from the database. Nothing is written to it.
* Predictions use the app's own code path (ml.TrendingPredictor, model/trending_model_v3.joblib)
  with only the inputs of the prediction form. The video's views, likes and comments are used
  ONLY to compute the actual outcome.
* "Actual" applies the label rule with the training thresholds (results/label_thresholds.json).
  The rule is defined at a video's FIRST trending appearance; videos that have trended for days
  have grown since, so a "published in the last 48 h" subset is reported separately.
* The API key is read from the repository .env and never printed.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from dotenv import dotenv_values
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
RESULTS = ROOT / "results"
sys.path.insert(0, str(REPO))
from ml import PredictionInput, TrendingPredictor  # noqa: E402
from ml.schemas import YOUTUBE_CATEGORY_IDS  # noqa: E402

API = "https://www.googleapis.com/youtube/v3"
COUNTRIES = ("AU", "CA", "GB", "IE", "IN", "NZ", "US", "ZA")


def _get(client, endpoint, **params):
    r = client.get(f"{API}/{endpoint}", params=params, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"YouTube API error {r.status_code} on {endpoint}: "
                         f"{r.json().get('error', {}).get('message', r.text[:200])}")
    return r.json()


def iso_seconds(value):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    d, h, mi, s = (int(x or 0) for x in m.groups()) if m else (0, 0, 0, 0)
    return float(d * 86400 + h * 3600 + mi * 60 + s)


def fetch_trending(key):
    rows = []
    with httpx.Client() as client:
        for cc in COUNTRIES:
            videos = _get(client, "videos", part="snippet,contentDetails,statistics", chart="mostPopular",
                          regionCode=cc, maxResults=50, key=key).get("items", [])
            ch_ids = sorted({v["snippet"]["channelId"] for v in videos})
            channels = {}
            for i in range(0, len(ch_ids), 50):
                for c in _get(client, "channels", part="statistics", id=",".join(ch_ids[i:i + 50]), key=key).get("items", []):
                    channels[c["id"]] = c.get("statistics", {})
            for rank, v in enumerate(videos, 1):
                sn, st, cd = v["snippet"], v.get("statistics", {}), v.get("contentDetails", {})
                ch = channels.get(sn["channelId"], {})
                rows.append({
                    "country": cc, "rank": rank, "video_id": v["id"],
                    "video_title": sn.get("title", ""), "video_description": sn.get("description", ""),
                    "video_tags": ",".join(sn.get("tags", [])), "channel_title": sn.get("channelTitle", ""),
                    "category": YOUTUBE_CATEGORY_IDS.get(sn.get("categoryId", ""), "Unknown"),
                    "video_duration_sec": iso_seconds(cd.get("duration")),
                    "video_published_at": sn.get("publishedAt"),
                    "channel_subscriber_count": int(ch.get("subscriberCount", 0) or 0),
                    "channel_video_count": int(ch.get("videoCount", 0) or 0),
                    "channel_view_count": int(ch.get("viewCount", 0) or 0),
                    "video_view_count": int(st.get("viewCount", 0) or 0),
                    "video_like_count": int(st.get("likeCount", 0) or 0),   # hidden likes -> 0, as in training
                    "video_comment_count": int(st.get("commentCount", 0) or 0),
                })
            print(f"{cc}: {len(videos)} trending videos", flush=True)
            time.sleep(0.5)
    return pd.DataFrame(rows)


def summarize(df, mask):
    part = df[mask & df["predicted"].notna()]
    out = {"videos": int(len(part)), "actual_positive_rate": round(float(part["actual"].mean()), 4)}
    if part["actual"].nunique() == 2:
        out.update({"roc_auc": round(float(roc_auc_score(part["actual"], part["predicted"])), 4),
                    "accuracy_at_0.5": round(float(((part["predicted"] >= 0.5) == part["actual"]).mean()), 4),
                    "mean_predicted": round(float(part["predicted"].mean()), 4)})
    return out


def main():
    key = dotenv_values(REPO / ".env").get("YOUTUBE_API_KEY")
    if not key:
        raise SystemExit("YOUTUBE_API_KEY missing in .env")
    fetched_at = datetime.now(timezone.utc)
    df = fetch_trending(key)
    published = pd.to_datetime(df["video_published_at"], utc=True)
    df["hours_since_published"] = ((pd.Timestamp(fetched_at) - published).dt.total_seconds() / 3600).round(1)

    th = json.loads((RESULTS / "label_thresholds.json").read_text())
    df["actual"] = ((df["video_view_count"] >= df["country"].map(th["view_threshold"]))
                    & (df["video_like_count"] >= df["country"].map(th["like_threshold"]))
                    & (df["video_comment_count"] >= df["country"].map(th["comment_threshold"]))).astype(int)

    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        device = "cpu"
    predictor = TrendingPredictor(device=device)
    supported = set(predictor.supported_categories)
    predicted = []
    for r in df.itertuples():
        if r.category not in supported:
            predicted.append(np.nan)   # the app rejects categories the model was not trained on
            continue
        predicted.append(predictor.predict(PredictionInput(
            category=r.category, country=r.country, video_duration_sec=r.video_duration_sec,
            channel_subscriber_count=r.channel_subscriber_count, channel_video_count=r.channel_video_count,
            channel_view_count=r.channel_view_count, video_title=r.video_title,
            video_description=r.video_description, video_tags=r.video_tags,
            channel_title=r.channel_title)).final_probability)
    df["predicted"] = predicted

    summary = {"fetched_at_utc": fetched_at.isoformat(timespec="seconds"),
               "model": predictor.artifact_path.name, "videos": int(len(df)),
               "rejected_categories": int(df["predicted"].isna().sum()),
               "all": summarize(df, np.ones(len(df), bool)),
               "published_last_48h": summarize(df, (df["hours_since_published"] <= 48).values),
               "accuracy_by_country": ((df["predicted"] >= 0.5) == (df["actual"] == 1))
               .groupby(df["country"]).mean().round(3).to_dict()}
    stamp = f"{fetched_at:%Y-%m-%d_%H%M}"
    cols = ["country", "rank", "video_id", "video_title", "channel_title", "category", "hours_since_published",
            "video_view_count", "video_like_count", "video_comment_count", "channel_subscriber_count",
            "actual", "predicted"]
    df[cols].to_csv(RESULTS / f"live_test_{stamp}.csv", index=False, encoding="utf-8-sig")
    (RESULTS / f"live_test_{stamp}.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"\nper-video table: ml_training/results/live_test_{stamp}.csv")


if __name__ == "__main__":
    main()
