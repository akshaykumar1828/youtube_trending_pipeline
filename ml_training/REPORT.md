# Prediction model: retraining report

The app now serves **model v3** (`model/trending_model_v3.joblib`). It replaced the original
model (v1), which was removed from the working tree (it remains in git history, commit 6ebf969).
This report explains what v3 is, how it was evaluated, and how it got there.

## October 2026 retrain: more data, less reliance on channel numbers

**Data.** Days 2026-01-06 → 2026-10-05 were appended from the Kaggle dataset
`canerkonuk/youtube-trending-videos-global` (`pushing_into_database/import_kaggle_trending.py`).
Training now uses 389,981 (video, country) first appearances of 204,258 videos (2024-10-12 →
2026-10-05); 6,818 snapshots without any statistics are left out. Label thresholds were
recomputed over the whole period (`results/label_thresholds.json`). Time split by video:
train → 2026-05-02, validation → 2026-07-19, test 2026-07-20 → 2026-10-05.

**Choosing how much the model may lean on channel numbers** (`numeric_reliance.py`,
`results/numeric_reliance.json`; fitted on train, scored on validation, 56,162 rows).
"Reliance" = ROC-AUC lost when each video gets another video's channel numbers; "wrong input"
= mean / 90th-percentile change of the probability when channel views are divided by 1000 and
subscribers multiplied by 10.

| Variant | ROC-AUC | Reliance | Wrong input (pts) |
|---|---|---|---|
| A: all 9 channel-number features (previous design) | 0.905 | 0.191 | 12.2 / 32.3 |
| B: raw sizes only (subscribers, channel views, video count) | 0.904 | 0.175 | 15.1 / 41.8 |
| B: subscribers only | 0.892 | 0.110 | 20.0 / 50.7 |
| D: no channel numbers | 0.875 | 0 | 0 / 0 |
| blend 70 % A + 30 % D | 0.904 | 0.114 | 8.5 / 22.5 |
| **blend 50 % A + 50 % D (chosen)** | **0.901** | **0.068** | **6.1 / 16.1** |
| blend 30 % A + 70 % D | 0.894 | 0.034 | 3.6 / 9.6 |

Removing features does not reduce sensitivity (the model leans harder on what is left); blending
a model that never sees channel numbers does. The app model is now the 50/50 logit blend
(`ml.features.blend`), both models stored in the one artifact.

**Results of the chosen model** (`results/train_v3.json`, fitted on train + validation):

| ROC-AUC | previous app model (to 2025-12-02) | **retrained blend (to 2026-07-19)** |
|---|---|---|
| Newest held-out period, 2026-07-20 → 2026-10-05 (60,616 rows) | 0.868 | **0.902** |
| Live: 398 videos on YouTube's trending lists, 2026-10-06 | 0.849 | **0.851** |
| Live, published in the last 48 h (207) | – | 0.843 |
| Live: mean change with wrong channel numbers | 15.3 pts | **7.5 pts** |

Held-out ROC-AUC by country: AU 0.901, CA 0.884, GB 0.893, IE 0.895, IN 0.943, NZ 0.899,
US 0.890, ZA 0.939. The sections below describe the original v3 evaluation (data to 2026-01-05,
single model); its numbers are not comparable with the table above (different, shorter test
period).

## Final result (original v3, data to 2026-01-05)

Both models scored on the **same rows with the same labels** (`compare_v1.py`, results in
`results/compare_v1_v3.json`):

| ROC-AUC | v1 (previous app model) | **v3 (app now)** |
|---|---|---|
| Newest held-out period, 2025-12-03 → 2026-01-05 (26,298 video-country rows) | 0.842 | **0.923** |
| Live: 397 videos on YouTube's trending lists on 2026-10-05 | 0.832 | **0.891** |
| Live, videos published in the last 48 h (153) | 0.808 | **0.896** |

| Live accuracy at a 0.5 cut-off | v1 | **v3** |
|---|---|---|
| All 397 videos | 70.8 % | **76.1 %** |
| Published in the last 48 h | 71.9 % | **80.4 %** |

v3 is better in every country on both tests (held-out / live ROC-AUC):

| Country | v1 | v3 | v1 live | v3 live |
|---|---|---|---|---|
| AU | 0.797 | **0.910** | 0.816 | **0.906** |
| CA | 0.828 | **0.909** | 0.821 | **0.857** |
| GB | 0.847 | **0.927** | 0.812 | **0.910** |
| IE | 0.821 | **0.922** | 0.752 | **0.851** |
| IN | 0.899 | **0.942** | 0.919 | **0.967** |
| NZ | 0.751 | **0.907** | 0.653 | **0.805** |
| US | 0.847 | **0.927** | 0.861 | **0.910** |
| ZA | 0.871 | **0.955** | 0.805 | **0.889** |

Other held-out metrics for v3 (`results/train_v3.json`): PR-AUC 0.837, log loss 0.320, Brier
0.096, calibration error 0.037; validation ROC-AUC 0.911.

Per-video live comparison: `results/live_test_2026-10-05_2121_final.csv`.

## What v3 predicts (unchanged meaning)

`high_performance_probability`: how likely a video that is **already trending** in a country is
to be a high performer there. It does not predict whether a video will become trending.

**Label** (the original rule): at the video's first trending appearance in that country,
views ≥ 100,000 × (country median views ÷ India median views) **and** likes ≥ country median
**and** comments ≥ country median. Medians are taken over all first trending appearances in each
country (thresholds in `results/label_thresholds.json`).

## Model

Gradient boosting (scikit-learn `HistGradientBoostingClassifier`: learning rate 0.03,
63 leaves, ≥ 100 rows per leaf, early stopping) on the features below. Since the October 2026
retrain there are two such models, one without the channel-number features, and the app returns
their 50/50 logit blend (see the first section).

- channel statistics and duration: the original 8 formulas (log subscribers, log channel views,
  channel authority, clipped views/subscribers per video, legacy-channel flag, video-volume bucket)
  plus video count, views per subscriber, short-video flags;
- category and country;
- title/description/tag signals from the raw text: whole-word keyword flags, `?`, `!`, digits,
  lengths, capital letters, non-Latin script, emoji, hashtags, links, tag count, "shorts",
  title–description overlap;
- text: LaBSE embedding (same pinned revision as before) of channel name + title + description +
  tags → a logistic-regression text score (out-of-fold during training, grouped by video) plus
  32 PCA components;
- recent rows weigh more in training: weight = exp(−age in days / 90).

The feature code lives in the app (`ml/features.py`) and training imports it, so training and
serving cannot drift apart. `make_reference.py` proves the app's per-request inference equals the
training pipeline (largest difference 1.6e-15) and writes `tests/fixtures/reference_predictions.json`.

**Training data:** one row per (video, country) first trending appearance in AU, CA, GB, IE, IN,
NZ, US, ZA, 2024-10-12 → 2025-12-02 (158,607 rows). The test period 2025-12-03 → 2026-01-05 was
never used for training or for any choice.

## How we got here (summary)

1. **Audit of the original notebook** (`model/final_model.ipynb` in git history): the served random
   forest had been retrained on only ~5,800 rows by `CalibratedClassifierCV(cv=2)`; the reported
   0.894 came from a different, unsaved forest on a random split; the stacking model learned from
   in-sample predictions; text order and cleaning differed between training and serving (commas
   removed without a space); most "psychology" features were constant or broken.
2. **Honest evaluation** (time split, validation for every choice, test once) put the served v1 at
   about 0.82 on new videos.
3. **v2** (one gradient-boosting model, fixed features, text components, recency weighting) was
   chosen on validation.
4. **Live test** on YouTube's current trending lists exposed that v2 under-rated big international
   videos in Ireland and New Zealand.
5. **v3**: one training row per (video, country) instead of one per video (the old de-duplication
   kept a single, alphabetically chosen country per video). No video appears in both training and
   test; training rows are cut at the end of their period.
6. **Label fix.** The label thresholds had been computed on the one-row-per-video data, which left
   Ireland and New Zealand with only ~1,300 / ~700 videos, mostly international hits: their view
   thresholds became 1.31 M / 1.35 M (likes 94 k / 112 k) instead of ~0.2–0.3 M. v2 and the first
   v3 were trained and scored with these distorted labels (their results files reflect them). The
   thresholds are now per-country medians over all first appearances; v3 was retrained and all
   final numbers above use the corrected labels. High-performer rates are now 37–41 % in every
   country.

Steps 2–5 were measured with the earlier labels; those numbers are not comparable with the
final ones and their result files were not kept.

## Limitations

- Scores videos that are **already trending**; not a trending-entry probability.
- Channel statistics are those of the time the video was trending (as in training).
- The high-performer share drifts: 37 % over all data, 32 % in the newest test period
  (2026-07-20 → 2026-10-05), 56 % in the live check of 2026-10-06. Ranking holds up (ROC-AUC
  above), but probabilities can be too low or too high for a new period; on that live check the
  average prediction (0.39) was below the actual rate (0.56). Periodic retraining or recalibration
  on recent data would help.
- The live "actual" uses current counts; for videos trending for several days this is later than
  their first appearance.
- LaBSE reads the first 256 tokens; with a long description the tags are cut off.
- Singapore is not supported (it was not in the training data).

## Files

| File | Purpose |
|---|---|
| `train_v3.py` | builds the data (read-only from PostgreSQL), trains, evaluates on the held-out period, writes `artifacts/trending_model_v3.joblib` and `results/label_thresholds.json` |
| `numeric_reliance.py` | compares how much the model may lean on channel numbers (variants A–D and blends; `results/numeric_reliance.json`) |
| `make_reference.py` | proves app inference = training pipeline, writes the test fixture |
| `compare_v1.py` | v1 vs v3 on the same rows (v1 read from git history) |
| `live_test.py` | scores today's YouTube trending lists with the app's model |
| `data.py`, `embed.py`, `common.py`, `throttle.py` | data loading, LaBSE embeddings, shared helpers, laptop load limits (6 CPU threads, small GPU batches, pauses) |
| `results/` | all numbers in this report |

## Retraining

Needs PostgreSQL with the raw tables (the repo `.env`), and a Python environment with the app's
packages plus `pyarrow` (optional: CUDA PyTorch for faster embeddings). New days can be added
first with `pushing_into_database/import_kaggle_trending.py` (then refresh the views). The
datasets and embeddings are cached in `ml_training/cache/`; **delete `cache/dataset.parquet` and
`cache/rows_video_country.parquet` after adding data**, or the new rows are not used (embeddings
are recomputed automatically when the texts change). Split dates follow the data (70/15/15 by
first appearance).

```powershell
cd ml_training
python -m venv .venv
.venv\Scripts\python -m pip install --index-url https://download.pytorch.org/whl/cu126 torch==2.12.1
.venv\Scripts\python -m pip install -r ..\backend\requirements-api.lock pyarrow
.venv\Scripts\python train_v3.py                  # evaluate + write artifacts/trending_model_v3.joblib
copy artifacts\trending_model_v3.joblib ..\model\trending_model_v3.joblib
python make_reference.py                          # regenerate the reference predictions
```

Then update `tests/fixtures/artifact_sha256.json` with the new checksum, run the test suites,
and rebuild the Docker image. `python live_test.py` checks the model on today's trending lists
(needs `YOUTUBE_API_KEY`).
