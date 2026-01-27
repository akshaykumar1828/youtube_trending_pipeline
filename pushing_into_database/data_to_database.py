import pandas as pd
from sqlalchemy import create_engine

# -----------------------------
# 1. PostgreSQL connection
# -----------------------------
engine = create_engine(
    "postgresql+psycopg2://postgres:PASSWORD@localhost:5432/youtube_trending_db"
)

# -----------------------------
# 2. CSV files → table mapping
# -----------------------------
files = {
    "youtube_trending_au": "Australia_youtube.csv",
    "youtube_trending_ca": "Canada_youtube.csv",
    "youtube_trending_in": "India_youtube.csv",
    "youtube_trending_ie": "Ireland_youtube.csv",
    "youtube_trending_nz": "New Zealand_youtube.csv",
    "youtube_trending_sg": "Singapore_youtube.csv",
    "youtube_trending_za": "South Africa_youtube.csv",
    "youtube_trending_gb": "United Kingdom_youtube.csv",
    "youtube_trending_us": "United States_youtube.csv"
}

# -----------------------------
# 3. EXACT column order in DB
# -----------------------------
db_columns = [
    "video_id",
    "video_published_at",
    "video_trending_date",
    "channel_id",
    "channel_title",
    "channel_description",
    "channel_custom_url",
    "channel_published_at",
    "channel_country",
    "video_title",
    "video_description",
    "video_default_thumbnail",
    "video_category_id",
    "video_tags",
    "video_duration",
    "video_dimension",
    "video_definition",
    "video_licensed_content",
    "video_view_count",
    "video_like_count",
    "video_comment_count",
    "channel_view_count",
    "channel_subscriber_count",
    "channel_have_hidden_subscribers",
    "channel_video_count",
    "channel_localized_title",
    "channel_localized_description",
    "video_trending_country"
]

# -----------------------------
# 4. Load each CSV
# -----------------------------
for table, file in files.items():
    print(f"Loading {file} -> {table}")

    df = pd.read_csv(file)

    # Fix column typo
    df = df.rename(columns={
        "video_trending__date": "video_trending_date"
    })

    # Fix dates
    df["video_trending_date"] = pd.to_datetime(
        df["video_trending_date"],
        errors="coerce"
    ).dt.date

    # Fix timestamps (REMOVE timezone)
    df["video_published_at"] = (
        pd.to_datetime(df["video_published_at"], errors="coerce", utc=True)
        .dt.tz_convert(None)
    )

    df["channel_published_at"] = (
        pd.to_datetime(df["channel_published_at"], errors="coerce", utc=True)
        .dt.tz_convert(None)
    )

    # Convert numeric columns
    int_cols = [
        "video_view_count",
        "video_like_count",
        "video_comment_count",
        "channel_view_count",
        "channel_subscriber_count",
        "channel_video_count"
    ]

    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")

    # Ensure boolean columns
    bool_cols = [
        "video_licensed_content",
        "channel_have_hidden_subscribers"
    ]

    for col in bool_cols:
        df[col] = df[col].fillna(False).astype(bool)

    # Reorder columns to match DB EXACTLY
    df = df[db_columns]

    # Insert into PostgreSQL
    df.to_sql(
        table,
        engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=1000
    )

    print(f"✅ {table} loaded successfully\n")

print("🎉 ALL FILES LOADED SUCCESSFULLY")
