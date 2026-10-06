"""Raw data loading and the video-level time split used by train_v3.py.

* `_load_raw()` reads the 8 supported countries' raw tables (read-only database session).
* `build_dataset()` keeps each video's FIRST trending appearance (deterministic: date, then
  country code) and assigns the time split by that date: train 70 % / validation 15 % /
  test 15 % (the newest videos). All country rows of a video then share its split, so no
  video is in both training and test. It also provides the per-video text for the embeddings.
"""

import numpy as np
import pandas as pd

from common import CACHE, COUNTRIES, read_only_engine

DATASET = CACHE / "dataset.parquet"

_COLUMNS = """
    video_id, video_published_at, video_trending_date, channel_id, channel_title,
    video_title, video_description, video_tags, video_category_id,
    EXTRACT(EPOCH FROM video_duration::interval)::float8 AS video_duration_sec,
    video_view_count, video_like_count, video_comment_count,
    channel_view_count, channel_subscriber_count, channel_video_count
"""


def _load_raw() -> pd.DataFrame:
    sql = " UNION ALL ".join(
        f"SELECT '{cc}'::text AS country, {_COLUMNS} FROM public.youtube_trending_{cc.lower()}"
        for cc in COUNTRIES)
    with read_only_engine().connect() as conn:
        return pd.read_sql(sql, conn)


def build_dataset(refresh=False) -> pd.DataFrame:
    if DATASET.exists() and not refresh:
        return pd.read_parquet(DATASET)

    raw = _load_raw()
    raw["video_trending_date"] = pd.to_datetime(raw["video_trending_date"]).dt.normalize()
    df = (raw.sort_values(["video_trending_date", "country", "video_id"], kind="mergesort")
             .drop_duplicates("video_id", keep="first")
             .reset_index(drop=True))
    for col in ("channel_title", "video_title", "video_description", "video_tags"):
        df[col] = df[col].fillna("").astype(str)

    dates = df["video_trending_date"]
    cut_val, cut_test = dates.quantile(0.70), dates.quantile(0.85)
    df["time_split"] = np.where(dates <= cut_val, "train", np.where(dates <= cut_test, "val", "test"))
    df.to_parquet(DATASET, index=False)
    return df
