from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import joblib
import numpy as np
import pandas as pd
import re
import os
from sentence_transformers import SentenceTransformer

# ==========================================
# App Setup
# ==========================================

app = FastAPI(title="YouTube Trending Predictor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# Paths (Render Compatible)
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "model")

# ==========================================
# Load Models
# ==========================================

text_lr = joblib.load(os.path.join(MODEL_DIR, "text_lr.pkl"))
text_scaler = joblib.load(os.path.join(MODEL_DIR, "text_scaler.pkl"))

rf_model = joblib.load(os.path.join(MODEL_DIR, "rf_calibrated.pkl"))
ohe = joblib.load(os.path.join(MODEL_DIR, "ohe.pkl"))

psych_lr = joblib.load(os.path.join(MODEL_DIR, "psych_lr.pkl"))
psych_scaler = joblib.load(os.path.join(MODEL_DIR, "psych_scaler.pkl"))

meta_lr = joblib.load(os.path.join(MODEL_DIR, "meta_lr.pkl"))

clip_values = joblib.load(os.path.join(MODEL_DIR, "clip_values.pkl"))
vpv_clip = clip_values["vpv_clip"]
spv_clip = clip_values["spv_clip"]

# Important: Load once globally (not inside route)
embedder = SentenceTransformer("sentence-transformers/LaBSE")

# ==========================================
# Request Schema
# ==========================================

class VideoInput(BaseModel):
    video_title: str
    video_description: str
    video_tags: str
    channel_title: str
    video_category: str
    country: str
    subs: int
    views: int
    vids: int
    duration: int

# ==========================================
# Helpers
# ==========================================

def clean_text(text):
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()

def has_any(text, word_set):
    text = f" {text} "
    return int(any(re.search(rf"\b{re.escape(w)}\b", text) for w in word_set))

URGENCY_WORDS = {"breaking","update","latest","alert","warning","today","now","live","urgent"}
HYPE_WORDS = {"viral","trending","trend","massive","huge","record","thriller"}
OFFICIAL_WORDS = {"official","announced","released","statement","report","confirms","results"}
EMOTION_WORDS = {"emotional","sad","angry","happy","proud","fear","panic","shocking"}

# ==========================================
# Routes
# ==========================================

@app.get("/")
def root():
    return {"message": "YouTube Trending Predictor API is running"}

@app.get("/model-info")
def model_info():
    return {
        "text_features": text_scaler.n_features_in_,
        "rf_features": rf_model.n_features_in_,
        "psych_features": psych_scaler.n_features_in_,
        "meta_features": meta_lr.n_features_in_
    }

@app.post("/predict")
def predict(data: VideoInput):

    try:

        # ---------- TEXT MODEL ----------
        combined_text = clean_text(
            f"{data.channel_title} {data.video_title} {data.video_description} {data.video_tags}"
        )

        emb = embedder.encode([combined_text], convert_to_numpy=True)

        if emb.shape[1] != text_scaler.n_features_in_:
            raise ValueError(
                f"Embedding size mismatch. Got {emb.shape[1]}, expected {text_scaler.n_features_in_}"
            )

        emb_scaled = text_scaler.transform(emb)
        text_prob = text_lr.predict_proba(emb_scaled)[0][1]

        # ---------- NUMERIC MODEL ----------
        vpv = min(data.views / max(1, data.vids), vpv_clip)
        spv = min(data.subs / max(1, data.vids), spv_clip)

        num_features = np.array([[
            np.log1p(data.duration),
            np.log1p(data.subs),
            np.log1p(data.views),
            np.log1p(data.views) * np.log1p(data.subs),
            np.log1p(vpv),
            np.log1p(spv),
            int(data.vids > 5000 and data.subs > 500_000),
            0 if data.vids < 200 else 1 if data.vids < 1000 else 2 if data.vids < 5000 else 3
        ]])

        cat_df = pd.DataFrame({
            "video_category_id": [data.video_category],
            "country": [data.country]
        })

        cat_features = ohe.transform(cat_df)

        if hasattr(cat_features, "toarray"):
            cat_features = cat_features.toarray()

        rf_input = np.hstack([cat_features, num_features])

        if rf_input.shape[1] != rf_model.n_features_in_:
            raise ValueError(
                f"RF feature mismatch. Got {rf_input.shape[1]}, expected {rf_model.n_features_in_}"
            )

        rf_prob = rf_model.predict_proba(rf_input)[0][1]

        # ---------- PSYCHOLOGY MODEL ----------
        has_urgency = has_any(combined_text, URGENCY_WORDS)
        has_hype = has_any(combined_text, HYPE_WORDS)
        has_official = has_any(combined_text, OFFICIAL_WORDS)
        has_emotion = has_any(combined_text, EMOTION_WORDS)

        has_number = int(bool(re.search(r"\d", data.video_title)))
        has_qmark = int("?" in data.video_title)
        has_excl = int("!" in data.video_title)

        title_words = set(data.video_title.lower().split())
        desc_words = set(data.video_description.lower().split())
        overlap_ratio = len(title_words & desc_words) / max(1, len(title_words))

        psych_features = psych_scaler.transform([[
            has_urgency,
            has_hype,
            has_official,
            has_emotion,
            has_number,
            has_qmark,
            has_excl,
            overlap_ratio
        ]])

        psych_prob = psych_lr.predict_proba(psych_features)[0][1]

        # ---------- META MODEL ----------
        final_prob = meta_lr.predict_proba(
            np.array([[text_prob, rf_prob, psych_prob]])
        )[0][1]

        # ---------- Confidence ----------
        if final_prob < 0.20:
            bucket = "Low chance"
        elif final_prob < 0.45:
            bucket = "Medium chance"
        elif final_prob < 0.70:
            bucket = "High chance"
        else:
            bucket = "Very high chance"

        return {
            "trending_probability": float(final_prob),
            "confidence_bucket": bucket,
            "model_breakdown": {
                "text_score": float(text_prob),
                "numeric_score": float(rf_prob),
                "psychology_score": float(psych_prob)
            }
        }

    except Exception as e:
        return {"error": str(e)}
