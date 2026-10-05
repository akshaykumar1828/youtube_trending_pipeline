"""Feature construction for the frozen trending model.

Copied verbatim from the legacy predictor.py (predict_trending). The model is a
frozen production artifact: this module must reproduce the legacy inference
behaviour exactly. Do NOT "fix" differences from the training notebook here.
"""

import re

import numpy as np
import pandas as pd


# Order of the 8 numeric columns appended after the one-hot block (RF input).
NUMERIC_FEATURES = (
    "log_video_duration_sec",
    "log_subscriber_count",
    "log_view_count",
    "channel_authority",
    "views_per_video_log",
    "subs_per_video_log",
    "legacy_channel",
    "video_volume_bucket",
)

# Order of the 8 psychology columns (psych_scaler / psych_lr input).
PSYCH_FEATURES = (
    "has_urgency",
    "has_hype",
    "has_official_words",
    "has_emotion",
    "has_number_in_title",
    "has_question_mark",
    "has_exclamation",
    "title_description_overlap_ratio",
)

# Frozen legacy behaviour: the legacy predictor sends these as constant 0.
# Kept as-is so inference output is unchanged.
LEGACY_CONSTANT_URGENCY = 0
LEGACY_CONSTANT_HYPE = 0
LEGACY_CONSTANT_OFFICIAL = 0
LEGACY_CONSTANT_EMOTION = 0
LEGACY_CONSTANT_OVERLAP_RATIO = 0


# ---------------------------------------------------
# TEXT CLEANING
# ---------------------------------------------------
def clean_text(text):

    if not isinstance(text, str):
        return ""

    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ---------------------------------------------------
# TEXT MODEL INPUT
# ---------------------------------------------------
def build_text(channel_title, video_title, video_description, video_tags):

    channel_title = clean_text(channel_title)
    title = clean_text(video_title)
    desc = clean_text(video_description)
    tags = clean_text(video_tags)

    return f"{channel_title} {title} {desc} {tags}".strip()


# ---------------------------------------------------
# NUMERIC FEATURES
# ---------------------------------------------------
def numeric_features(video_duration_sec, channel_subscriber_count,
                     channel_video_count, channel_view_count,
                     vpv_clip, spv_clip):

    subs = channel_subscriber_count
    views = channel_view_count
    vids = channel_video_count
    dur = video_duration_sec

    log_video_duration_sec = np.log1p(dur)
    log_subscriber_count = np.log1p(subs)
    log_view_count = np.log1p(views)

    views_per_video = views / max(1, vids)
    subs_per_video = subs / max(1, vids)

    views_per_video = min(views_per_video, vpv_clip)
    subs_per_video = min(subs_per_video, spv_clip)

    views_per_video_log = np.log1p(views_per_video)
    subs_per_video_log = np.log1p(subs_per_video)

    channel_authority = np.log1p(views) * np.log1p(subs)

    legacy_channel = int((vids > 5000) and (subs > 500000))

    video_volume_bucket = (
        0 if vids < 200 else
        1 if vids < 1000 else
        2 if vids < 5000 else
        3
    )

    return np.array([[

        log_video_duration_sec,
        log_subscriber_count,
        log_view_count,
        channel_authority,
        views_per_video_log,
        subs_per_video_log,
        legacy_channel,
        video_volume_bucket

    ]])


# ---------------------------------------------------
# CATEGORICAL FEATURES (input to the saved OneHotEncoder)
# ---------------------------------------------------
def categorical_frame(category, country):

    return pd.DataFrame({

        "video_category_id": [str(category)],
        "country": [country]

    })


# ---------------------------------------------------
# PSYCHOLOGICAL FEATURES
# ---------------------------------------------------
def psych_features(video_title):

    title = clean_text(video_title)

    has_number = int(bool(re.search(r"\d", title)))
    has_qmark = int("?" in video_title)
    has_excl = int("!" in video_title)

    return np.array([[

        LEGACY_CONSTANT_URGENCY,
        LEGACY_CONSTANT_HYPE,
        LEGACY_CONSTANT_OFFICIAL,
        LEGACY_CONSTANT_EMOTION,
        has_number,
        has_qmark,
        has_excl,
        LEGACY_CONSTANT_OVERLAP_RATIO

    ]])
