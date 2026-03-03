import pandas as pd
from sqlalchemy import create_engine
from googleapiclient.discovery import build
from datetime import datetime
import isodate

# ------------------------------------------------
# 1. CONFIG
# ------------------------------------------------
API_KEY = "AIzaSyD8FUlM2WEFm4_O_Y-xwBloWA04Oo52fk8"
DB_USER = "postgres"
DB_PASSWORD = quote_plus("hsk@2006")  
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "youtube"
engine = create_engine(
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

youtube = build("youtube", "v3", developerKey=API_KEY)

# ------------------------------------------------
# 2. Countries & Table Mapping
# ------------------------------------------------
countries = {
    "AU": "youtube_trending_au",
    "CA": "youtube_trending_ca",
    "IN": "youtube_trending_in",
    "IE": "youtube_trending_ie",
    "NZ": "youtube_trending_nz",
    "SG": "youtube_trending_sg",
    "ZA": "youtube_trending_za",
    "GB": "youtube_trending_gb",
    "US": "youtube_trending_us",
}

# ------------------------------------------------
# 3. DB Column Order 
# ------------------------------------------------
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

# ------------------------------------------------
# 4. Fetch Trending Videos Per Country
# ------------------------------------------------
def fetch_trending(country_code):
    request = youtube.videos().list(
        part="snippet,contentDetails,statistics",
        chart="mostPopular",
        regionCode=country_code,
        maxResults=50
    )
    response = request.execute()
    return response.get("items", [])

# ------------------------------------------------
# 5. Fetch Channel Details
# ------------------------------------------------
def fetch_channel_details(channel_ids):
    request = youtube.channels().list(
        part="snippet,statistics",
        id=",".join(channel_ids)
    )
    response = request.execute()
    return {item["id"]: item for item in response.get("items", [])}

# ------------------------------------------------
# 6. MAIN INGESTION LOOP
# ------------------------------------------------
for country_code, table_name in countries.items():
    print(f"\nFetching {country_code} trending videos...")

    videos = fetch_trending(country_code)

    if not videos:
        print("No videos found.")
        continue

    channel_ids = list(set(video["snippet"]["channelId"] for video in videos))
    channel_data = fetch_channel_details(channel_ids)

    rows = []

    for video in videos:
        snippet = video["snippet"]
        stats = video.get("statistics", {})
        content = video.get("contentDetails", {})

        channel_id = snippet["channelId"]
        channel = channel_data.get(channel_id, {})
        channel_snippet = channel.get("snippet", {})
        channel_stats = channel.get("statistics", {})

        # Convert ISO 8601 duration
        duration = None
        if "duration" in content:
            duration = int(isodate.parse_duration(content["duration"]).total_seconds())

        row = {
            "video_id": video["id"],
            "video_published_at": pd.to_datetime(snippet.get("publishedAt")),
            "video_trending_date": datetime.utcnow().date(),
            "channel_id": channel_id,
            "channel_title": snippet.get("channelTitle"),
            "channel_description": channel_snippet.get("description"),
            "channel_custom_url": channel_snippet.get("customUrl"),
            "channel_published_at": pd.to_datetime(channel_snippet.get("publishedAt")),
            "channel_country": channel_snippet.get("country"),
            "video_title": snippet.get("title"),
            "video_description": snippet.get("description"),
            "video_default_thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url"),
            "video_category_id": snippet.get("categoryId"),
            "video_tags": ",".join(snippet.get("tags", [])),
            "video_duration": duration,
            "video_dimension": content.get("dimension"),
            "video_definition": content.get("definition"),
            "video_licensed_content": content.get("licensedContent", False),
            "video_view_count": int(stats.get("viewCount", 0)),
            "video_like_count": int(stats.get("likeCount", 0)),
            "video_comment_count": int(stats.get("commentCount", 0)),
            "channel_view_count": int(channel_stats.get("viewCount", 0)),
            "channel_subscriber_count": int(channel_stats.get("subscriberCount", 0)),
            "channel_have_hidden_subscribers": channel_stats.get("hiddenSubscriberCount", False),
            "channel_video_count": int(channel_stats.get("videoCount", 0)),
            "channel_localized_title": channel_snippet.get("localized", {}).get("title"),
            "channel_localized_description": channel_snippet.get("localized", {}).get("description"),
            "video_trending_country": country_code
        }

        rows.append(row)

    df = pd.DataFrame(rows)
    df = df[db_columns]

    df.to_sql(
        table_name,
        engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=1000
    )

    print(f"✅ {table_name} loaded successfully")

print("\n🎉 ALL COUNTRIES INGESTED SUCCESSFULLY")
