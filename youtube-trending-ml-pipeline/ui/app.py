import streamlit as st
import plotly.express as px
import pandas as pd
from data_loader import load_data
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from predictor import predict_trending


st.set_page_config(
    page_title="YouTube Trending Dashboard",
    layout="wide"
)


# ---------------- FORMAT NUMBERS ----------------
def format_number(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}K"
    else:
        return str(int(n))


# ---------------- NAVIGATION ----------------
page = st.sidebar.radio("Navigation", ["Dashboard", "Predict"])


# =================================================
# ================= DASHBOARD =====================
# =================================================
if page == "Dashboard":

    df = load_data()

    st.title("YouTube Trending Analytics Dashboard")

    # ------------------------------------------------
    # CREATE COUNTRY COLUMN (for will_trend logic)
    # ------------------------------------------------
    df["country"] = df["video_trending_country"]

    # ------------------------------------------------
    # CREATE WILL_TREND COLUMN (training logic)
    # ------------------------------------------------
    INDIA_BASE_VIEWS = 100000

    country_median_views = (
    df.groupby("country")["video_view_count"]
    .median()
    )   

    # detect India automatically
    if "IN" in country_median_views.index:
        india_median = country_median_views.loc["IN"]
    elif "India" in country_median_views.index:
        india_median = country_median_views.loc["India"]
    else:
        india_median = country_median_views.median()

    scaling_factor = country_median_views / india_median

    view_th = scaling_factor * INDIA_BASE_VIEWS

    like_th = df.groupby("country")["video_like_count"].median()
    comment_th = df.groupby("country")["video_comment_count"].median()

    df["will_trend"] = (
        (df["video_view_count"] >= df["country"].map(view_th)) &
        (df["video_like_count"] >= df["country"].map(like_th)) &
        (df["video_comment_count"] >= df["country"].map(comment_th))
    ).astype(int)

    # ------------------------------------------------
    # FILTERS
    # ------------------------------------------------
    st.sidebar.header("Filters")

    country = st.sidebar.selectbox(
        "Trending Country",
        ["All"] + sorted(df["country"].dropna().unique())
    )

    category = st.sidebar.selectbox(
        "Video Category",
        ["All"] + sorted(df["video_category_id"].dropna().unique())
    )

    filtered_df = df.copy()

    if country != "All":
        filtered_df = filtered_df[
            filtered_df["country"] == country
        ]

    if category != "All":
        filtered_df = filtered_df[
            filtered_df["video_category_id"] == category
        ]

    # ------------------------------------------------
    # APPLY WILL_TREND
    # ------------------------------------------------
    trending_df = filtered_df[
        filtered_df["will_trend"] == 1
    ]

    unique_videos = trending_df.drop_duplicates("video_id")

    avg_views = unique_videos["video_view_count"].mean()
    avg_likes = unique_videos["video_like_count"].mean()

    # ------------------------------------------------
    # KPI CARDS
    # ------------------------------------------------
    k1, k2, k3, k4 = st.columns(4)

    k1.metric("Trending Videos", format_number(len(unique_videos)))
    k2.metric("Avg Views", format_number(avg_views))
    k3.metric("Avg Likes", format_number(avg_likes))
    k4.metric(
        "Unique Channels",
        format_number(unique_videos["channel_title"].nunique())
    )

    # =================================================
    # CATEGORY ANALYSIS
    # =================================================
    col1, col2 = st.columns(2)

    with col1:

        category_counts = (
            unique_videos["video_category_id"]
            .value_counts()
            .reset_index()
        )

        category_counts.columns = ["Category", "Videos"]

        fig1 = px.bar(
            category_counts,
            x="Category",
            y="Videos",
            title="Trending Videos by Category",
            labels={"Videos": "Number of Videos"}
        )

        st.plotly_chart(fig1, use_container_width=True)

    with col2:

        if len(category_counts) > 1:

            fig2 = px.pie(
                category_counts,
                names="Category",
                values="Videos",
                hole=0.5,
                title="Category Share"
            )

            st.plotly_chart(fig2, use_container_width=True)

        else:
            st.info("Only one category selected")

    # =================================================
    # CHANNEL ANALYSIS
    # =================================================
    col3, col4 = st.columns(2)

    with col3:

        top_channels = (
            unique_videos["channel_title"]
            .value_counts()
            .head(10)
            .reset_index()
        )

        top_channels.columns = ["Channel", "Videos"]

        fig3 = px.bar(
            top_channels,
            x="Videos",
            y="Channel",
            orientation="h",
            title="Top Trending Channels"
        )

        st.plotly_chart(fig3, use_container_width=True)

    with col4:

        country_counts = (
            trending_df["country"]
            .value_counts()
            .reset_index()
        )

        country_counts.columns = ["Country", "Trending Videos"]

        fig4 = px.bar(
            country_counts,
            x="Country",
            y="Trending Videos",
            title="Videos Predicted to Trend by Country"
        )

        st.plotly_chart(fig4, use_container_width=True)

    # =================================================
    # ENGAGEMENT ANALYSIS
    # =================================================
    col5, col6 = st.columns(2)

    with col5:

        fig5 = px.scatter(
            unique_videos,
            x="video_view_count",
            y="video_like_count",
            color="country",
            title="Views vs Likes",
            labels={
                "video_view_count": "Views",
                "video_like_count": "Likes"
            }
        )

        st.plotly_chart(fig5, use_container_width=True)

    with col6:

        fig6 = px.histogram(
            unique_videos,
            x="video_view_count",
            nbins=40,
            title="Views Distribution"
        )

        st.plotly_chart(fig6, use_container_width=True)

    # =================================================
    # TRENDING TIMELINE
    # =================================================
    if "video_trending_date" in trending_df.columns:

        trending_df["video_trending_date"] = pd.to_datetime(
            trending_df["video_trending_date"]
        )

        timeline = trending_df.groupby(
            trending_df["video_trending_date"].dt.date
        ).size()

        fig7 = px.line(
            x=timeline.index,
            y=timeline.values,
            title="Trending Videos Over Time",
            labels={
                "x": "Date",
                "y": "Trending Videos"
            }
        )

        st.plotly_chart(fig7, use_container_width=True)


# =================================================
# ================= PREDICT PAGE ==================
# =================================================
elif page == "Predict":

    st.title("YouTube Trending Predictor")

    video_title = st.text_input("Video Title")
    video_description = st.text_area("Video Description")
    video_tags = st.text_input("Video Tags")
    channel_title = st.text_input("Channel Title")

    video_category_id = st.text_input("Video Category ID")
    country = st.selectbox(
        "Country Code",
        ["IN", "US", "GB", "NZ", "SG", "ZA"]
    )

    video_duration_sec = st.number_input("Video Duration (seconds)", min_value=0)
    channel_subscriber_count = st.number_input("Subscribers", min_value=0)
    channel_video_count = st.number_input("Total channel Videos", min_value=0)
    channel_view_count = st.number_input("Total channel Views", min_value=0)

    if st.button("Predict"):

        user_input = {
            "video_title": video_title,
            "video_description": video_description,
            "video_tags": video_tags,
            "channel_title": channel_title,
            "video_category_id": video_category_id,
            "country": country,
            "video_duration_sec": video_duration_sec,
            "channel_subscriber_count": channel_subscriber_count,
            "channel_video_count": channel_video_count,
            "channel_view_count": channel_view_count
        }

        result = predict_trending(user_input)

        st.metric("Trending Probability", f"{result['final_probability']*100:.2f}%")
        st.write("Text Score:", result["text_score"])
        st.write("Numeric Score:", result["numeric_score"])
        st.write("Psych Score:", result["psychology_score"])

    