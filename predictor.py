import numpy as np
import pandas as pd
import re
import joblib
import os
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------
# PATH SETUP (MATCHES YOUR TREE)
# ---------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "model")


# ---------------------------------------------------
# LOAD MODELS
# ---------------------------------------------------
import streamlit as st

@st.cache_resource
def load_models():

    embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

    text_scaler = joblib.load(os.path.join(MODEL_DIR, "text_scaler.pkl"))
    text_lr = joblib.load(os.path.join(MODEL_DIR, "text_lr.pkl"))

    rf_calibrated = joblib.load(os.path.join(MODEL_DIR, "rf_calibrated.pkl"))

    psych_scaler = joblib.load(os.path.join(MODEL_DIR, "psych_scaler.pkl"))
    psych_lr = joblib.load(os.path.join(MODEL_DIR, "psych_lr.pkl"))

    meta_lr = joblib.load(os.path.join(MODEL_DIR, "meta_lr.pkl"))

    return embedder, text_scaler, text_lr, rf_calibrated, psych_scaler, psych_lr, meta_lr

clip_values = joblib.load(os.path.join(MODEL_DIR, "clip_values.pkl"))
vpv_clip = clip_values["vpv_clip"]
spv_clip = clip_values["spv_clip"]

# ---------------------------------------------------
# CLEAN TEXT
# ---------------------------------------------------
def clean_text(text):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ---------------------------------------------------
# MAIN FUNCTION
# ---------------------------------------------------
def predict_trending(user_input):

    # ---- TEXT ----
    channel_title = clean_text(user_input.get("channel_title", ""))
    title = clean_text(user_input.get("video_title", ""))
    desc = clean_text(user_input.get("video_description", ""))
    tags = clean_text(user_input.get("video_tags", ""))

    combined_text = f"{channel_title} {title} {desc} {tags}".strip()

    text_emb = embedder.encode([combined_text], convert_to_numpy=True)
    text_emb = text_scaler.transform(text_emb)
    text_prob = text_lr.predict_proba(text_emb)[:, 1][0]

    # ---- NUMERIC ----
    subs = user_input["channel_subscriber_count"]
    views = user_input["channel_view_count"]
    vids = user_input["channel_video_count"]
    dur = user_input["video_duration_sec"]

    log_video_duration_sec = np.log1p(dur)
    log_subscriber_count = np.log1p(subs)
    log_view_count = np.log1p(views)

    # same logic as training
    views_per_video = views / max(1, vids)
    subs_per_video  = subs / max(1, vids)

    # clipping (same as notebook)
    views_per_video = min(views_per_video, vpv_clip)
    subs_per_video  = min(subs_per_video, spv_clip)

    views_per_video_log = np.log1p(views_per_video)
    subs_per_video_log  = np.log1p(subs_per_video)
    channel_authority = np.log1p(views) * np.log1p(subs)
    legacy_channel = int((vids > 5000) and (subs > 500_000))

    video_volume_bucket = (
        0 if vids < 200 else
        1 if vids < 1000 else
        2 if vids < 5000 else
        3
    )

    num_features = np.array([[ 
        log_video_duration_sec,
        log_subscriber_count,
        log_view_count,
        channel_authority,
        views_per_video_log,
        subs_per_video_log,
        legacy_channel,
        video_volume_bucket
    ]])
    print("STREAMLIT NUM FEATURES:", num_features)

    cat_df = pd.DataFrame({
        "video_category_id": [str(user_input["video_category_id"])],
        "country": [user_input["country"]]
    })

    cat_feature = ohe.transform(cat_df)
    rf_input = np.hstack([cat_feature, num_features])
    rf_prob = rf_calibrated.predict_proba(rf_input)[:, 1][0]

    # ---- PSYCH ----
    has_number = int(bool(re.search(r"\d", title)))
    has_qmark = int("?" in user_input.get("video_title", ""))
    has_excl = int("!" in user_input.get("video_title", ""))

    overlap_ratio = 0

    psych_features = np.array([[0,0,0,0,has_number,has_qmark,has_excl,overlap_ratio]])
    psych_features = psych_scaler.transform(psych_features)
    psych_prob = psych_lr.predict_proba(psych_features)[:, 1][0]

    # ---- META ----
    final_prob = meta_lr.predict_proba(
        np.array([[text_prob, rf_prob, psych_prob]])
    )[:, 1][0]

    return {
        "final_probability": round(float(final_prob), 4),
        "text_score": round(float(text_prob), 4),
        "numeric_score": round(float(rf_prob), 4),
        "psychology_score": round(float(psych_prob), 4)
    }