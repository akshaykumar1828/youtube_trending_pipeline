"""Append new days from the Kaggle dataset "Youtube Trending Videos Dataset - Daily Update"
(canerkonuk/youtube-trending-videos-global, CC0) to the 9 raw tables.

The Kaggle data has the same 27 columns as public.youtube_trending_<cc> (it is the same
YouTube API collection: on the overlapping days 2025-12-01..2026-01-05 all 64,462 rows match).
Differences handled here: the date column is `video_trending__date` in YYYY.MM.DD text, every
value is text, and counts are sometimes written with a decimal point ("617137.0").
Rows with a malformed date, duration or count (the file has some column-shifted rows in other
countries) are skipped and reported.

Append-only and safe to re-run:
  * for each country, only rows dated AFTER the table's current latest date are inserted,
    so existing rows are never changed and nothing is inserted twice;
  * duplicate (country, video, date) rows in the source are dropped;
  * all 9 tables are written in ONE transaction (all or nothing); --dry-run rolls back.

Afterwards refresh the application views (as the admin user):
    REFRESH MATERIALIZED VIEW CONCURRENTLY app.trending_snapshots;
    REFRESH MATERIALIZED VIEW CONCURRENTLY app.video_details;

Usage (repository root; admin credentials from .env):
    python pushing_into_database/import_kaggle_trending.py <path/to/youtube_trending_videos_global.parquet> [--dry-run]
"""

import argparse
import csv
import io
import sys
from pathlib import Path

import pandas as pd
import psycopg2
import pyarrow.parquet as pq
from dotenv import dotenv_values

REPO = Path(__file__).resolve().parent.parent
TABLES = {"Australia": "au", "Canada": "ca", "United Kingdom": "gb", "Ireland": "ie", "India": "in",
          "New Zealand": "nz", "Singapore": "sg", "United States": "us", "South Africa": "za"}
# Raw-table columns (without will_trend, which only the original model's label script wrote).
COLUMNS = [
    "video_id", "video_published_at", "video_trending_date", "channel_id", "channel_title",
    "channel_description", "channel_custom_url", "channel_published_at", "channel_country",
    "video_title", "video_description", "video_default_thumbnail", "video_category_id", "video_tags",
    "video_duration", "video_dimension", "video_definition", "video_licensed_content",
    "video_view_count", "video_like_count", "video_comment_count", "channel_view_count",
    "channel_subscriber_count", "channel_have_hidden_subscribers", "channel_video_count",
    "channel_localized_title", "channel_localized_description", "video_trending_country",
]
COUNTS = ["video_view_count", "video_like_count", "video_comment_count", "channel_view_count",
          "channel_subscriber_count", "channel_video_count"]
BOOLEANS = ["video_licensed_content", "channel_have_hidden_subscribers"]
TIMESTAMPS = ["video_published_at", "channel_published_at"]


def connect():
    cfg = dotenv_values(REPO / ".env")
    return psycopg2.connect(host=cfg.get("DB_HOST") or "localhost", port=int(cfg.get("DB_PORT") or 5432),
                            dbname=cfg["DB_NAME"], user=cfg.get("DB_USER") or "postgres",
                            password=cfg["DB_PASSWORD"], application_name="import_kaggle_trending")


def latest_dates(cur):
    out = {}
    for country, cc in TABLES.items():
        cur.execute(f"SELECT max(video_trending_date) FROM public.youtube_trending_{cc}")
        out[country] = cur.fetchone()[0]
    return out


def valid_rows(df):
    """Rows whose date, duration and counts have the expected shape."""
    ok = df["video_trending__date"].str.fullmatch(r"\d{4}\.\d{2}\.\d{2}", na=False)
    ok &= df["video_duration"].str.fullmatch(r"P[0-9DTHMS.]*", na=False)
    for col in COUNTS:
        ok &= df[col].isna() | df[col].eq("") | df[col].str.fullmatch(r"\d+(\.0+)?", na=False)
    return ok


def prepare(df):
    ok = valid_rows(df)
    if (~ok).any():
        print(f"skipping {int((~ok).sum())} malformed rows")
    df = df[ok].copy()
    df["video_trending_date"] = pd.to_datetime(df["video_trending__date"], format="%Y.%m.%d").dt.date
    for col in TIMESTAMPS:   # ISO 8601 UTC -> naive UTC, like the existing rows
        ts = pd.to_datetime(df[col].replace("", None), format="ISO8601", utc=True, errors="coerce")
        df[col] = ts.dt.tz_localize(None).astype("string").replace({"NaT": None})
    for col in COUNTS:
        # Same convention as the existing rows (verified on 658,761 overlapping rows): an empty
        # string (count hidden / not returned) is stored as 0, a missing value (null) as NULL.
        df[col] = pd.to_numeric(df[col].mask(df[col].eq(""), "0"), errors="coerce").round().astype("Int64")
    # Newer source rows write hidden likes/comments as null instead of "". When the video's views
    # were returned, a missing like/comment count is a hidden one: 0, as in the existing rows.
    # Rows where YouTube returned no statistics at all (views null too) stay NULL.
    has_views = df["video_view_count"].notna()
    for col in ("video_like_count", "video_comment_count"):
        df.loc[has_views & df[col].isna(), col] = 0
    for col in BOOLEANS:
        low = df[col].astype("string").str.strip().str.lower()
        # A missing flag is stored as false in the existing rows (167 of 167 overlapping cases).
        df[col] = low.map({"true": True, "false": False}).astype("boolean").fillna(False)
    text_cols = [c for c in COLUMNS if c not in COUNTS + BOOLEANS + TIMESTAMPS + ["video_trending_date"]]
    for col in text_cols:    # COPY cannot carry NUL characters
        df[col] = df[col].astype("string").str.replace("\x00", "", regex=False)
    return df.drop_duplicates(["video_trending_country", "video_id", "video_trending_date"])


def copy_rows(cur, table, rows):
    buf = io.StringIO()
    rows[COLUMNS].to_csv(buf, index=False, header=False, quoting=csv.QUOTE_NONNUMERIC, na_rep="")
    buf.seek(0)
    # Empty non-text fields are NULL (missing count / date); empty text stays an empty string.
    force_null = ", ".join(COUNTS + BOOLEANS + TIMESTAMPS)
    cur.copy_expert(f"COPY public.{table} ({', '.join(COLUMNS)}) FROM STDIN "
                    f"WITH (FORMAT csv, FORCE_NULL ({force_null}))", buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parquet")
    ap.add_argument("--dry-run", action="store_true", help="insert inside the transaction, report, then roll back")
    args = ap.parse_args()

    conn = connect()
    try:
        with conn.cursor() as cur:
            latest = latest_dates(cur)
            start = min(latest.values())
            print("current latest dates:", {c: str(d) for c, d in latest.items()})
            src = pq.read_table(args.parquet, filters=[("video_trending_country", "in", list(TABLES)),
                                                        ("video_trending__date", ">", start.strftime("%Y.%m.%d"))])
            df = prepare(src.to_pandas())
            print(f"source rows after {start}: {len(df)} (9 countries, duplicates removed)")
            total = 0
            for country, cc in TABLES.items():
                rows = df[(df["video_trending_country"] == country) & (df["video_trending_date"] > latest[country])]
                if len(rows):
                    copy_rows(cur, f"youtube_trending_{cc}", rows)
                total += len(rows)
                rng = f"{rows['video_trending_date'].min()} .. {rows['video_trending_date'].max()}" if len(rows) else "-"
                print(f"  youtube_trending_{cc}: +{len(rows)} rows ({rng})")
        if args.dry_run:
            conn.rollback()
            print(f"DRY RUN: {total} rows would be inserted; rolled back")
        else:
            conn.commit()
            print(f"committed: {total} rows inserted")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
