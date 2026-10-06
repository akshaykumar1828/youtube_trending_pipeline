# YouTube Trending Intelligence

A web application for exploring YouTube's trending lists across nine countries and for
scoring videos with a machine-learning model trained on those lists. It is a React
dashboard on top of a FastAPI backend and a PostgreSQL database, with user accounts,
workspaces and roles, and a Docker Compose setup for running the whole thing.

The project started as a Streamlit dashboard plus a model notebook and was rebuilt into
the application described here (see [Project evolution](#project-evolution)).

---

## Why this exists

YouTube publishes a "most popular" (trending) list per country, but only as a moving
snapshot: today's list replaces yesterday's. To answer questions like *which categories
dominate trending in India compared with the US*, *how long do videos stay on the list*,
or *which channels keep appearing*, you need the history.

This project collects those daily snapshots into PostgreSQL and puts an analytics UI and
an API on top of them. It also serves a model that estimates how likely a
**video that is already trending** is to be one of the stronger performers in its
country.

## What you can do with it

- **Overview**: trending volume, unique videos, views, engagement rate and unique
  channels for a date range, each compared with the previous period of the same length;
  a daily trend chart (total, by country or by category).
- **Trending videos**: a searchable, sortable, paginated list of every video that trended
  in the selected period.
- **Video details**: one video's metadata, channel information and its full trending
  history across countries and days.
- **Analytics**: category performance, country performance, engagement distribution
  (histogram, percentiles, per-category spread, views-vs-engagement scatter) and top
  channels.
- **ML predictions**: enter a video's title, description, tags, channel statistics,
  duration, category and country and get a `high_performance_probability` plus the
  score of the text alone.
- **Accounts and teams**: sign up (which creates your own workspace), sign in, and, as an
  owner or admin, add teammates and manage their roles.

All dashboard pages share one set of filters (date range, countries, categories) that
lives in the URL, so a filtered view can be bookmarked or shared.

---

## Architecture

```
 YouTube Data API v3 ("mostPopular" chart, 9 countries)
          │  pushing_into_database/data_ingestion_api_v3.py
          ▼
 PostgreSQL ── public.youtube_trending_<cc>   9 raw tables (source data, never modified by the app)
          │   app.trending_snapshots          materialized view: one row per country × video × day
          │   app.video_details               materialized view: one row per video
          │   auth.*                          users, workspaces, memberships, sessions
          ▼
 FastAPI backend  (/api/v1, read-only analytics role + separate auth role)
          ▼
 React frontend  (Vite build; served by nginx in Docker)
          ▼
 Browser
```

The prediction path is separate from the analytics path and does not touch the
database:

```
 Browser form ─▶ POST /api/v1/predictions ─▶ PredictionService (one in-memory model, one call at a time)
                                              └─▶ ml.TrendingPredictor (model/trending_model_v3.joblib)
                                                   ├─ LaBSE text embedding → text score (logistic regression) + 32 PCA components
                                                   ├─ channel statistics, duration, category, country
                                                   ├─ title / description / tag signals
                                                   └─ gradient boosting on all of the above → high_performance_probability
```

In Docker, nginx serves the built frontend and proxies `/api` and `/health` to FastAPI on
the same origin, so the browser only ever talks to one host.

## Data

**Where it comes from.** `pushing_into_database/data_ingestion_api_v3.py` calls the
YouTube Data API v3 `videos.list(chart="mostPopular")` for AU, CA, GB, IE, IN, NZ, SG, US
and ZA (top 50 per country per run), fetches channel statistics for those videos, and
appends one row per video to that country's table (`public.youtube_trending_au`, …),
stamped with the run date. Running it once a day builds the history.

**How it is stored.** The application never reads the raw tables directly. Migrations
build two materialized views in the `app` schema:

| View | One row per | Used for |
|---|---|---|
| `app.trending_snapshots` | country × video × trending date | all filtered analytics, the video list, video history |
| `app.video_details` | video | the video detail page (metadata from the video's latest snapshot anywhere) |

The views keep only the columns the application needs, normalise empty categories to
`Unknown`, and convert durations to seconds. They are refreshed manually after new data
is ingested (`REFRESH MATERIALIZED VIEW ...`); nothing refreshes them automatically.

**Single source of data.** The application and the model training read PostgreSQL only, so
analytics always reflect the database, and the database is the single place where data is
added. (Earlier CSV exports of the data are no longer part of the repository; they remain in
git history.)

In the database this repository was developed against, the data covers 2024-10-12 to
2026-10-05: 1,135,886 snapshots of 217,115 distinct videos. Days after 2026-01-05 were
appended from the public Kaggle dataset "YouTube Trending Videos Dataset - Daily Update"
(canerkonuk/youtube-trending-videos-global, CC0), which comes from the same YouTube API
collection (all 64,462 overlapping rows match), with
`pushing_into_database/import_kaggle_trending.py`; it only adds days newer than each table's
latest date and never changes existing rows.

## How to read the numbers

These definitions come from the SQL in `backend/app/repositories/` and are also in the
API's own description. They matter: several numbers that look similar are counted
differently.

| Metric | Level | Meaning |
|---|---|---|
| **Trending volume** | snapshot | Number of (country, video, day) appearances. A video trending in 3 countries for 5 days adds 15. |
| **Unique videos** | video | Distinct videos. Each video is counted once no matter how many days or countries. |
| **Views** | video | Sum of each video's view count **from its latest snapshot within the filters**. View counts are YouTube's lifetime, global totals at fetch time, so historical snapshots are never summed and there is no "views per day". |
| **Engagement rate** | video | `(likes + comments) / views`, summed over the same latest snapshots (a ratio of sums, not an average of per-video ratios). |
| **Unique channels** | video | Distinct channels among those videos. |
| **Country views** (`views_of_trending_videos`) | country | Global views of the videos that trended in that country. **Not** views from that country, and **not additive** across countries (a video trending in 4 countries is counted in each). |
| **Category volume share** | snapshot | A category's share of trending volume. |
| **Category unique videos** | video | Videos whose latest filtered snapshot is in that category; these add up to the overall unique-video count. |
| **Days on trending** | video | Distinct dates the video appears within the filters. |

Other rules:

- **"Latest snapshot"** always means the latest one *inside the active filters* (most recent
  date, then highest view count, then country code), not the latest one overall. The video
  detail page is the exception: it shows the video's globally latest snapshot and full,
  unfiltered history.
- **Period change** compares with the immediately preceding period of equal length and the
  same countries/categories. Counts and views change in **percent**; engagement rate changes
  in **percentage points**. If the previous period would start before the first date in
  the data, no comparison is shown.
- Because views are lifetime totals, a "views" change compares two different sets of videos;
  it is not views gained.
- With no date filter, the dashboard shows the last 30 days ending at the latest date in the
  database.

## The prediction model

**What it predicts.** The output is called `high_performance_probability`. The model was
trained **only on videos that were already on a trending list**, one row per video and
country. A video is labelled high-performing in a country when, at its first trending
appearance there, its likes and comments are at or above that country's median and its
views are at or above `100,000 × (country median views / India median views)`. Medians are
taken over all first trending appearances in each country.

**What it does not predict.** It does not estimate whether an arbitrary video will reach a
trending list. It scores how likely a video, *if it is trending*, is to be among the higher
performers in its country. Treat it as a relative indicator.

**Inputs.** Title, description, tags, channel title, category (name or YouTube category
ID), country, duration in seconds, channel subscriber count, channel video count and
channel view count. Supported countries: AU, CA, GB, IE, IN, NZ, US, ZA (Singapore is not
supported). Supported categories: the 15 in the training data (Autos & Vehicles, Comedy,
Education, Entertainment, Film & Animation, Gaming, Howto & Style, Music, News & Politics,
Nonprofits & Activism, People & Blogs, Pets & Animals, Science & Technology, Sports, Travel &
Events). Anything else is rejected with a clear validation error.

**How it works (model v3).** Two gradient-boosting models look at the inputs together:

- **Text**: LaBSE (`sentence-transformers/LaBSE`, multilingual) embeds channel name, title,
  description and tags; a logistic regression turns the embedding into a *text score*
  (also shown on the page), and 32 compressed components of the embedding are used directly.
- **Channel and video**: log-scaled channel statistics, channel ratios, duration and
  short-video flags.
- **Category and country.**
- **Title/description/tag signals**: keywords, digits, `?` and `!`, lengths, capitals, emoji,
  hashtags, links, tag count.

One model uses all of these; the other uses everything **except the channel numbers**
(subscribers, channel views, video count). The result is their 50/50 blend (an average of
log-odds), so channel size cannot outweigh the content: a wrong channel number moves a
prediction about half as much as it would with the channel model alone. This costs very
little accuracy (validation ROC-AUC 0.901 vs 0.905).

**How good it is.** Trained on 2024-10-12 – 2026-07-19. On the newest period, never used
for training or model choice (2026-07-20 – 2026-10-05, 60,616 video-country rows), it reaches
ROC-AUC **0.902**; the previous app model (trained to 2025-12-02) scores 0.868 on the same rows.
On a live check with 398 videos taken straight from YouTube's trending lists on 2026-10-06,
it reached 0.851 (previous app model 0.849 on the same videos), while entering wrong channel
numbers (views ÷1000, subscribers ×10) moved its predictions 7.5 points on average versus 15.3
for the previous model. Details, per-country results and the full history are in
[ml_training/REPORT.md](ml_training/REPORT.md).

**Where it lives.** `model/trending_model_v3.joblib` (one file holding both models, checksum-verified by the tests
and the Docker build), inference code in `ml/`, training code in `ml_training/`. The feature
code in `ml/features.py` is shared by training and serving, and the tests check that the app
reproduces 25 reference predictions of the training pipeline. `scikit-learn` is pinned to
1.8.0 because the model file was saved with it.

## Accounts, workspaces and roles

- **Register** (`/register`) creates an account **and a new workspace** and makes you its
  **Owner**. There is no built-in or default account: the first person to register on a
  fresh database simply becomes the owner of their own workspace.
- **Sign in / sign out** use a server-side session. The browser holds only an HttpOnly
  cookie (`yt_session`); the database stores an HMAC of the token, never the token itself.
  Sessions last 8 hours by default. Signing out deletes the session on the server.
- **Workspaces** (called tenants in the code) own users and memberships. The YouTube data is
  shared and read-only for everyone; it is not copied per workspace.
- **Roles and permissions:**

  | Role | View analytics | Make predictions | Manage users |
  |---|---|---|---|
  | Owner | ✓ | ✓ | ✓ |
  | Admin | ✓ | ✓ | ✓ |
  | Member | ✓ | ✓ | – |

  Only an owner can create owners or change an owner. Nobody can change their own role or
  status, and every workspace keeps at least one active owner. Deactivating someone signs
  them out everywhere.
- Everything under `/api/v1` except register, login and logout requires a session, and the
  permission checks run in FastAPI. Hiding a menu item in the UI is a convenience, not the
  protection.

## Running it

### Option A: Docker (whole stack)

Requirements: Docker with Compose v2, about 6 GB of memory for Docker, and a dump of the
raw tables to seed the new database (the Compose database starts empty). The complete
procedure (configuration, building, seeding, migrating, ports, HTTPS notes) is in
**[DEPLOYMENT.md](DEPLOYMENT.md)**. The short version:

```powershell
Copy-Item .env.example .env            # then fill in the passwords and AUTH_SECRET_KEY
docker compose --profile tools build
docker compose up -d db
docker compose run --rm dbtools seed     # needs deploy/seed/raw_tables.dump, see DEPLOYMENT.md
docker compose run --rm dbtools migrate
docker compose up -d                     # open http://localhost:8080
```

### Option B: local development

Requirements: Python 3.14 (the version the pinned dependencies and the Docker image use),
Node.js 20.19+ or 22.12+, PostgreSQL 18 with its `psql` client, and a database that already
contains the raw `public.youtube_trending_*` tables (created by the ingestion script).

```powershell
# 1. Configuration: copy and fill in the database names/passwords and AUTH_SECRET_KEY
Copy-Item .env.example .env

# 2. Python dependencies (application + tests)
python -m pip install -r requirements-dev.txt

# 3. Build the app schema, views and roles in your database, then give the two
#    application roles their passwords (read from .env)
python backend/scripts/migrate.py apply
python backend/scripts/migrate.py set-app-role-password
python backend/scripts/migrate.py set-auth-role-password
python backend/scripts/migrate.py status

# 4. API on http://localhost:8000 (the first start downloads LaBSE, ~1.8 GB)
python -m uvicorn app.main:app --app-dir backend --reload

# 5. Frontend on http://localhost:5173 (second terminal)
cd frontend
npm ci
Copy-Item .env.example .env              # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Interactive API docs are at http://localhost:8000/docs when `APP_ENV=development`.

### First use

1. Open the app (http://localhost:5173 in development, http://localhost:8080 in Docker).
   You are sent to the sign-in page.
2. Choose **Create a workspace**, enter your name, email and a password of at least 12
   characters. You are signed in as the Owner of the new workspace.
3. Explore **Overview**, **Trending**, **Analytics** and **Predictions**; click a video to see
   its details and history.
4. Under **Team**, add colleagues with an initial password and a role.

## API at a glance

All endpoints return JSON. Successful responses use `{"data": ...}` (filtered analytics
add `"filters"` with the filters that were actually applied); errors use
`{"error": {"code", "message", "field", "request_id"}}`. Analytics endpoints accept
`start_date`, `end_date`, and repeatable `country` and `category` parameters.

| Area | Endpoints |
|---|---|
| Health (public) | `GET /health/live`, `GET /health/ready` |
| Auth | `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me` |
| Workspace | `GET /api/v1/tenant`, `GET/POST /api/v1/tenant/members`, `PATCH /api/v1/tenant/members/{user_id}` |
| Filters | `GET /api/v1/meta/filters` |
| Overview | `GET /api/v1/overview/kpis`, `GET /api/v1/overview/daily-volume` |
| Analytics | `GET /api/v1/analytics/categories`, `.../countries`, `.../engagement`, `.../channels` |
| Videos | `GET /api/v1/videos`, `GET /api/v1/videos/{video_id}`, `GET /api/v1/videos/{video_id}/history` |
| Predictions | `GET /api/v1/predictions/model-info`, `POST /api/v1/predictions` |

The full contract is in `frontend/openapi.json` (a snapshot of the backend's OpenAPI
schema) and in [PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md#8-api-reference).

## Tests

```powershell
python -m pytest backend/tests     # API, auth/RBAC, repositories, database roles, migrations
python -m pytest tests             # ML: model checksum, reference predictions, validation

cd frontend
npm run test:run                   # component/page tests (Vitest + Testing Library + MSW)
npm run lint
npm run typecheck
npm run build
npm run format:check
npm run api:check                  # generated API types match frontend/openapi.json
```

The backend tests run against the real development database (with migrations applied)
and some assert values from the current dataset; the ML tests load the real model.
`deploy/smoke_test.py` checks a running Docker stack over HTTP.

At the time of writing: 347 backend tests, 73 ML tests and 169 frontend tests pass.

## Repository layout

| Path | What it is |
|---|---|
| `backend/app/` | FastAPI application: routes, auth, repositories (SQL), schemas, services |
| `backend/migrations/` | Numbered SQL migrations (read model, roles, auth schema) |
| `backend/scripts/migrate.py` | Migration runner (applies migrations, sets role passwords) |
| `backend/tests/` | Backend tests |
| `ml/` | Inference package and feature code for the model (shared with training) |
| `model/` | The model file `trending_model_v3.joblib` |
| `ml_training/` | Training, evaluation and live-check scripts, the report and results |
| `tests/` | ML tests and fixtures (model checksum, reference predictions) |
| `frontend/` | React + TypeScript app, nginx config and its Dockerfile |
| `deploy/` | Docker helpers: database tool image, LaBSE pinning, artifact check, smoke test |
| `docker-compose.yml` | The Docker deployment |
| `pushing_into_database/` | YouTube Data API ingestion script |

## Limitations

- **Data freshness is manual.** Ingestion is a script you run; the materialized views must be
  refreshed afterwards. There is no scheduler.
- **The prediction is narrow** (see above): already-trending videos only, eight countries,
  fifteen categories, training data up to December 2025. The share of high performers drifts
  over time, so probabilities can be too low or too high for a new period (ranking holds up
  better); periodic retraining is needed. See [ml_training/REPORT.md](ml_training/REPORT.md).
- **Authentication basics only**: no password reset, email verification, invitations, MFA
  or SSO. Lockout is per account (5 failed attempts → 15 minutes); there is no per-IP rate
  limiting. Self-registration is open by default (`AUTH_REGISTRATION_ENABLED`).
- **No HTTPS in the Docker stack.** nginx listens on plain HTTP; a TLS-terminating proxy is
  needed for anything beyond localhost. The session cookie is `Secure`, which browsers
  accept on `http://localhost` only.
- **Single API process.** One uvicorn worker per container by design (the model is loaded per
  process); predictions are processed one at a time.
- **Tests depend on the development database** and its current data.

## Future work

Ideas that are **not implemented**: scheduled ingestion and view refresh, password reset
and email verification, per-IP rate limiting, TLS in the Compose stack, published images
and CI, scheduled retraining or recalibration of the prediction model.

## Project evolution

1. **Original project**: daily ingestion from the YouTube API into PostgreSQL, a training
   notebook for a stacked model (three sub-models and a combiner), and a Streamlit dashboard
   that read the CSV exports.
2. **Full-stack application**: an analytics read model in PostgreSQL, a FastAPI backend and
   a React frontend replaced the Streamlit UI; accounts, workspaces and roles were added, and
   the stack was containerised. The original model was first served unchanged.
3. **Model v3**: an audit of the original training found several defects (the served random
   forest had been trained on ~7.5 % of the data, training and serving prepared text
   differently, most title features did not work). The model was rebuilt and evaluated on the
   newest data and on live trending lists, and replaced the original one
   ([ml_training/REPORT.md](ml_training/REPORT.md)). The original notebook, Streamlit
   dashboard and model files remain in git history.

More detail for developers: **[PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)**.
Deployment: **[DEPLOYMENT.md](DEPLOYMENT.md)**.
