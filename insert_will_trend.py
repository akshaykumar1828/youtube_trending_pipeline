import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine(
    "postgresql+psycopg2://postgres:2818@localhost:5432/youtube_trending_db"
)

tables = {
    "IN": "youtube_trending_in",
    "US": "youtube_trending_us",
    "GB": "youtube_trending_gb",
    "CA": "youtube_trending_ca",
    "AU": "youtube_trending_au",
    "IE": "youtube_trending_ie",
    "NZ": "youtube_trending_nz",
    "SG": "youtube_trending_sg",
    "ZA": "youtube_trending_za"
}

dfs = []

for country, table in tables.items():
    print(f"Reading {table}")
    df = pd.read_sql(
        f"""
        SELECT
            video_id,
            video_view_count,
            video_like_count,
            video_comment_count
        FROM {table}
        """,
        engine
    )
    df["country"] = country
    dfs.append(df)

df_all = pd.concat(dfs, ignore_index=True)

INDIA_BASE_VIEWS = 100_000

# Median views per country
country_median_views = (
    df_all.groupby("country")["video_view_count"].median()
)

india_median = country_median_views.loc["IN"]

# Scaling factor
scaling_factor = country_median_views / india_median

# View threshold
view_th = scaling_factor * INDIA_BASE_VIEWS

# Like & comment thresholds
like_th = df_all.groupby("country")["video_like_count"].median()
comment_th = df_all.groupby("country")["video_comment_count"].median()

df_all["will_trend"] = (
    (df_all["video_view_count"] >= df_all["country"].map(view_th)) &
    (df_all["video_like_count"] >= df_all["country"].map(like_th)) &
    (df_all["video_comment_count"] >= df_all["country"].map(comment_th))
).astype("int8")

tmp_df = df_all[["video_id", "country", "will_trend"]]

tmp_df.to_sql(
    "tmp_will_trend",
    engine,
    if_exists="replace",
    index=False
)

with engine.begin() as conn:

    for country, table in tables.items():
        print(f"Updating {table}")

        conn.execute(text(f"""
            UPDATE {table} t
            SET will_trend = tmp.will_trend
            FROM tmp_will_trend tmp
            WHERE t.video_id = tmp.video_id
              AND tmp.country = :country
        """), {"country": country})

with engine.begin() as conn:
    conn.execute(text("DROP TABLE IF EXISTS tmp_will_trend"))
