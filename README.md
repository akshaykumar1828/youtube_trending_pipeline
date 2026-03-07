# YouTube Trending Insight Pipeline

A machine learning pipeline that predicts the probability of a YouTube video trending using **text embeddings, channel analytics, and ensemble learning**.  
The project also includes an **interactive Streamlit dashboard** for exploring trending patterns across multiple countries.

---

# Project Overview

This project analyzes YouTube video metadata to estimate whether a video is likely to trend.

The prediction system uses information available at upload time such as:

- Video title
- Video description
- Tags
- Channel statistics
- Video duration
- Category
- Country

The model combines **text features, channel engagement metrics, and psychological signals** to generate a **trending probability score**.

---

# Machine Learning Pipeline

The system uses a **stacked ensemble architecture** consisting of three specialized models.

## 1. Text Model

Extracts semantic meaning from video metadata.

Embedding Model: **LaBSE Multilingual Transformer**

Features used:
- Video title
- Description
- Tags
- Channel title

Classifier:
- Logistic Regression

---

## 2. Channel & Numeric Model

Captures creator authority and engagement patterns.

Engineered features include:

- log subscriber count
- log channel view count
- video duration
- channel authority score
- views per video
- subscribers per video
- channel activity bucket

Model used:

**Random Forest (Calibrated)**

---

## 3. Psychological Signals Model

Captures virality-related signals in titles and descriptions.

Features include:

- urgency keywords
- hype words
- emotional language
- numbers in titles
- punctuation signals
- title–description overlap

Model used:

**Logistic Regression**

---

## 4. Meta Model (Stacking)

Outputs from the three models are combined using:

**Logistic Regression Stacking**

Final output:

```
Trending Probability Score
```

---

# Model Performance

Evaluation metric:

```
ROC-AUC Score ≈ 0.89
```

The stacked model significantly improves performance compared to individual models.

---

# Dataset

The dataset contains **YouTube trending videos from multiple countries**.

Countries included:

- Australia
- Canada
- India
- Ireland
- New Zealand
- Singapore
- South Africa
- United Kingdom
- United States

Each dataset contains video metadata, channel statistics, and engagement metrics.

---

# Interactive Dashboard

A **multi-page Streamlit dashboard** was developed to explore the dataset and model predictions.

Dashboard features include:

### Prediction
Predict trending probability for a new video.

### Category Analytics
Trending distribution across video categories.

### Country Analytics
Trending patterns across different countries.

### Top Channels
Channels that appear most frequently in trending lists.

### Views Distribution
Distribution of views among trending videos.

### Category vs Country Heatmap
Category popularity across regions.

---

# Project Structure

```
youtube-trending-ml-pipeline
│
├── dataset_csv_files
│
├── model
│   ├── text_lr.pkl
│   ├── text_scaler.pkl
│   ├── rf_calibrated.pkl
│   ├── psych_lr.pkl
│   ├── psych_scaler.pkl
│   └── meta_lr.pkl
│
├── predictor.py
├── insert_will_trend.py
│
├── ui
│   ├── app.py
│   ├── data_loader.py
│   └── pages
│       ├── category_analytics.py
│       ├── country_analytics.py
│       ├── category_country_heatmap.py
│       ├── top_channels.py
│       └── views_distribution.py
│
└── README.md
```

---

# Technologies Used

- Python
- Pandas
- NumPy
- Scikit-Learn
- Sentence Transformers
- Streamlit
- Matplotlib
- Seaborn
- Joblib

---

# Running the Project Locally

### Install dependencies

```
pip install -r requirements.txt
```

---

### Run the Streamlit dashboard

```
streamlit run ui/app.py
```

---

### Open the app in your browser

```
http://localhost:8501
```

---

# Example Output

```
Final Probability: 0.86
Text Score: 0.73
Numeric Score: 0.73
Psychology Score: 0.50
```

---

# Future Improvements

Possible future improvements include:

- YouTube API data ingestion
- Real-time trending prediction
- Cloud deployment
- Automated model retraining
- Feature importance visualization

---

# Author

Machine Learning project focused on **content virality prediction and YouTube analytics pipelines**.
