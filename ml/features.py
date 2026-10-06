"""Feature construction for the YouTube trending model (v3).

This module is the single definition of the model's features: the training code
(ml_training/) imports these functions, so training and serving cannot drift apart.
Every function works on a pandas DataFrame (one row per video and country) with the
columns of the prediction input: video_title, video_description, video_tags,
channel_title, video_category_id, country, video_duration_sec,
channel_subscriber_count, channel_video_count, channel_view_count.

Changing anything here changes predictions; retrain and regenerate the reference
predictions (tests/fixtures/reference_predictions.json) if you do.
"""

import re
import unicodedata

import numpy as np
import pandas as pd

# Order of the 8 base channel/duration features.
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
CATEGORICAL_FEATURES = ("video_category_id", "country")
# Features computed from the channel's numbers (subscribers, channel views, video count).
# The second model of the blend is trained without them (see blend()).
CHANNEL_NUMBER_FEATURES = (
    "log_subscriber_count", "log_view_count", "channel_authority", "views_per_video_log",
    "subs_per_video_log", "legacy_channel", "video_volume_bucket", "log_video_count",
    "log_views_per_sub",
)

# Keyword lists (whole-word matches on title, description and tags).
URGENCY_WORDS = {
    "breaking", "update", "latest", "alert", "warning", "today", "now", "live", "just in", "urgent",
    "ताजा", "ताज़ा", "बड़ी खबर", "आज", "अभी", "सीधा प्रसारण",
    "இப்போ", "செய்தி", "உடனடி", "తాజా", "వార్త", "తక్షణం", "খবর", "আজ", "এখন",
    "urgent", "alerte", "dernière", "direct", "eilmeldung", "aktuell", "warnung", "live",
    "urgente", "última", "ahora", "alerta",
}
HYPE_WORDS = {
    "viral", "trending", "trend", "massive", "huge", "record", "historic", "unbelievable", "insane",
    "वायरल", "ट्रेंडिंग", "रिकॉर्ड", "வைரல்", "டிரெண்டிங்", "వైరల్", "ట్రెండింగ్", "ভাইরাল", "ট্রেন্ডিং",
    "viral", "tendance", "énorme", "viral", "trend", "riesig", "viral", "tendencia", "enorme",
}
OFFICIAL_WORDS = {
    "official", "announced", "released", "statement", "report", "confirms", "results", "highlights",
    "आधिकारिक", "घोषणा", "परिणाम", "रिपोर्ट", "அதிகாரபூர்வ", "அறிக்கை", "అధికారిక", "ప్రకటన",
    "ফলাফল", "ঘোষণা", "রিপোর্ট", "officiel", "annonce", "rapport", "résultats", "offiziell",
    "bericht", "ergebnisse", "oficial", "anuncio", "informe", "resultados",
}
EMOTION_WORDS = {
    "emotional", "sad", "angry", "happy", "proud", "fear", "panic", "shocking", "heartbreaking",
    "भावुक", "डर", "गुस्सा", "खुशी", "உணர்ச்சி", "பயம்", "భయం", "ఆవేదన", "আবেগ", "ভয়",
    "émotionnel", "choquant", "peur", "emotional", "schockierend", "angst",
    "emocional", "impactante", "miedo",
}
KEYWORD_SETS = {"urgency": URGENCY_WORDS, "hype": HYPE_WORDS, "official": OFFICIAL_WORDS,
                "emotion": EMOTION_WORDS}


# ---------------------------------------------------------------------------------------
# Text for the LaBSE embedding
# ---------------------------------------------------------------------------------------
def clean_text(text):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_text(channel_title, video_title, video_description, video_tags):
    """Channel title, title, description and tags, cleaned and joined. LaBSE reads the
    first 256 tokens, so with a very long description the tags are cut off."""
    parts = (clean_text(channel_title), clean_text(video_title),
             clean_text(video_description), clean_text(video_tags))
    return " ".join(parts).strip()


def texts(df):
    return [build_text(c, t, d, g) for c, t, d, g in
            zip(df["channel_title"], df["video_title"], df["video_description"], df["video_tags"])]


# ---------------------------------------------------------------------------------------
# Channel statistics and duration
# ---------------------------------------------------------------------------------------
def numeric_features(video_duration_sec, channel_subscriber_count, channel_video_count,
                     channel_view_count, vpv_clip, spv_clip):
    """The 8 base features for one video, as a (1, 8) array."""
    subs, views = channel_subscriber_count, channel_view_count
    vids, dur = channel_video_count, video_duration_sec

    log_video_duration_sec = np.log1p(dur)
    log_subscriber_count = np.log1p(subs)
    log_view_count = np.log1p(views)

    views_per_video = min(views / max(1, vids), vpv_clip)
    subs_per_video = min(subs / max(1, vids), spv_clip)
    views_per_video_log = np.log1p(views_per_video)
    subs_per_video_log = np.log1p(subs_per_video)

    channel_authority = np.log1p(views) * np.log1p(subs)
    legacy_channel = int((vids > 5000) and (subs > 500_000))
    video_volume_bucket = 0 if vids < 200 else 1 if vids < 1000 else 2 if vids < 5000 else 3

    return np.array([[log_video_duration_sec, log_subscriber_count, log_view_count, channel_authority,
                      views_per_video_log, subs_per_video_log, legacy_channel, video_volume_bucket]])


def channel_features(df, vpv_clip, spv_clip):
    rows = [numeric_features(d, s, v, cv, vpv_clip, spv_clip)[0]
            for d, s, v, cv in zip(df["video_duration_sec"], df["channel_subscriber_count"],
                                   df["channel_video_count"], df["channel_view_count"])]
    out = pd.DataFrame(np.asarray(rows, dtype=float), columns=list(NUMERIC_FEATURES), index=df.index)
    out["log_video_count"] = np.log1p(df["channel_video_count"])
    out["duration_sec"] = df["video_duration_sec"]
    out["is_short_60"] = (df["video_duration_sec"] <= 60).astype(int)
    out["is_short_180"] = (df["video_duration_sec"] <= 180).astype(int)
    out["log_views_per_sub"] = np.log1p(df["channel_view_count"] / df["channel_subscriber_count"].clip(lower=1))
    return out


# ---------------------------------------------------------------------------------------
# Title / description / tag signals (computed on the RAW text, so '?' and '!' count)
# ---------------------------------------------------------------------------------------
def _cleaned_words(text):
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def _word_flag(text, words):
    return int(any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text) for w in words))


def _emoji_count(s):
    return sum(1 for ch in s if unicodedata.category(ch) == "So" or ord(ch) >= 0x1F000)


def content_features(df):
    title, desc, tags = df["video_title"], df["video_description"], df["video_tags"]
    low = (title + " " + desc + " " + tags.str.replace(",", " ")).str.lower()
    out = pd.DataFrame(index=df.index)
    for name, words in KEYWORD_SETS.items():
        out[f"kw_{name}"] = low.map(lambda x, w=words: _word_flag(x, w))
    out["title_has_digit"] = title.str.contains(r"\d", regex=True).astype(int)
    out["title_has_question"] = title.str.contains("?", regex=False).astype(int)
    out["title_has_exclamation"] = title.str.contains("!", regex=False).astype(int)
    out["title_len"] = title.str.len()
    out["title_words"] = title.str.split().str.len().fillna(0)
    letters = title.map(lambda s: sum(ch.isalpha() for ch in s))
    out["title_upper_ratio"] = title.map(lambda s: sum(ch.isupper() for ch in s)) / letters.clip(lower=1)
    out["title_non_ascii_ratio"] = title.map(lambda s: sum(ord(ch) > 127 for ch in s)) / title.str.len().clip(lower=1)
    out["title_emoji"] = title.map(_emoji_count)
    out["title_hashtags"] = title.str.count("#")
    out["title_has_pipe_or_dash"] = title.str.contains(r"[|\-–—]", regex=True).astype(int)
    out["desc_len_log"] = np.log1p(desc.str.len())
    out["desc_links"] = desc.str.count("http")
    out["desc_hashtags"] = desc.str.count("#")
    out["tag_count"] = tags.map(lambda s: len([t for t in s.split(",") if t.strip()]))
    out["shorts_marker"] = low.str.contains("shorts", regex=False).astype(int)
    tc, dc = title.map(_cleaned_words), desc.map(_cleaned_words)
    out["title_desc_overlap"] = [len(set(a.split()) & set(b.split())) / max(1, len(set(a.split())))
                                 for a, b in zip(tc, dc)]
    return out


# ---------------------------------------------------------------------------------------
# Model input table
# ---------------------------------------------------------------------------------------
def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def blend(p_full, p_no_channel, weight):
    """Final probability: logit average of the model with channel numbers and the model
    without them (`weight` on the latter). Halves how much channel numbers can move a
    prediction, so a wrong subscriber/view count cannot dominate the title and text."""
    z = (1 - weight) * logit(p_full) + weight * logit(p_no_channel)
    return 1 / (1 + np.exp(-z))


def model_table(df, vpv_clip, spv_clip, text_probability, text_components):
    """Rows for the gradient-boosting model: channel/duration, title signals, category and
    country (pandas categoricals), the text score (as logit) and the PCA text components."""
    parts = [channel_features(df, vpv_clip, spv_clip).reset_index(drop=True),
             content_features(df).reset_index(drop=True),
             df[list(CATEGORICAL_FEATURES)].reset_index(drop=True).astype(str).astype("category")]
    table = pd.concat(parts, axis=1)
    table["text_logit"] = logit(text_probability)
    for i in range(text_components.shape[1]):
        table[f"text_pc{i}"] = text_components[:, i]
    return table
