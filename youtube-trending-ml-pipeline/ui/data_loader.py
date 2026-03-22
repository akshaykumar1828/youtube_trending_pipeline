import pandas as pd
import os
import streamlit as st


@st.cache_data
def load_data():

    folder = os.path.join(os.path.dirname(__file__), "..", "dataset_csv_files")

    files = [
        "Australia_youtube.csv",
        "Canada_youtube.csv",
        "India_youtube.csv",
        "Ireland_youtube.csv",
        "New Zealand_youtube.csv",
        "Singapore_youtube.csv",
        "South Africa_youtube.csv",
        "United Kingdom_youtube.csv",
        "United States_youtube.csv"
    ]

    dfs = []

    for file in files:
        path = os.path.join(folder, file)

        df = pd.read_csv(path, low_memory=False)   # also removes warning

        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)