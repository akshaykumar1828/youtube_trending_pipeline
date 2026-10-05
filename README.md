# YouTube Trending Intelligence

A web application for exploring YouTube's trending lists across nine countries and for
scoring videos with a machine-learning model trained on those lists. It is a React
dashboard on top of a FastAPI backend and a PostgreSQL database, with user accounts,
workspaces and roles, and a Docker Compose setup for running the whole thing.

The project started as a Streamlit dashboard plus a model notebook (both still in this
repository, see [Project evolution](#project-evolution)) and was rebuilt into the
application described here.

---

## Why this exists

YouTube publishes a "most popular" (trending) list per country, but only as a moving
snapshot: today's list replaces yesterday's. To answer questions like *which categories
dominate trending in India compared with the US*, *how long do videos stay on the list*,
or *which channels keep appearing*, you need the history.

This project collects those daily snapshots into PostgreSQL and puts an analytics UI and
an API on top of them. It also serves a frozen model that estimates how likely a
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
  duration, category and country and get a `high_performance_probability` with its three
  component scores.
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
                                              └─▶ ml.TrendingPredictor
                                                   ├─ LaBSE text embedding  → text logistic regression
                                                   ├─ channel/duration/category/country → calibrated random forest
                                                   ├─ title signals         → "psychology" logistic regression
                                                   └─ stacking logistic regression → high_performance_probability
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

**CSV files.** `dataset_csv_files/` holds CSV exports of the per-country data (tracked with
Git LFS, ~1.3 GB). Only the legacy Streamlit dashboard reads them. The current application
reads PostgreSQL exclusively, so analytics always reflect the database, and the database
is the single place where data is added.

In the database this repository was developed against, the data covers 2024-10-12 to
2026-01-05: 658,761 snapshots of 99,402 distinct videos.

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
trained **only on videos that were already on a trending list**. A video was labelled
high-performing when, at its first trending appearance, its likes and comments were at or
above its country's median and its views were at or above
`100,000 × (country median views / India median views)` (see `insert_will_trend.py`, which
wrote that label as `will_trend`).

**What it does not predict.** It does not estimate whether an arbitrary video will reach a
trending list. It scores how likely a video, *if it is trending*, is to be among the higher
performers in its country. Treat it as a relative indicator.

**Inputs.** Title, description, tags, channel title, category (name or YouTube category
ID), country, duration in seconds, channel subscriber count, channel video count and
channel view count. Supported countries: AU, CA, GB, IE, IN, NZ, US, ZA (Singapore is not
supported). Supported categories: the 14 the model was trained on (Autos & Vehicles,
Comedy, Education, Entertainment, Film & Animation, Gaming, Howto & Style, Music, News &
Politics, People & Blogs, Pets & Animals, Science & Technology, Sports, Travel & Events).
Anything else is rejected with a clear validation error.

**How it works.** Three sub-models are combined by a logistic regression:

1. **Text**: LaBSE (`sentence-transformers/LaBSE`, multilingual) embeds channel title,
   title, description and tags; a logistic regression scores the embedding.
2. **Channel and numeric**: a calibrated random forest on log-scaled channel statistics,
   duration, channel ratios and one-hot category/country.
3. **Psychology**: a logistic regression on title signals. Some of these signals are fixed
   at 0 at inference, exactly as in the original application, so only digits, `?` and `!` in
   the title change this score.

The training notebook reports ROC-AUC ≈ 0.894 on a held-out split (computed with the
uncalibrated forest; the served pipeline has not been separately evaluated).
`GET /api/v1/predictions/model-info` returns the full description, supported values and
known limitations.

**Why it is frozen.** The artifacts in `model/` are served exactly as trained. They are not
retrained or re-saved, the inference code in `ml/` reproduces the original `predictor.py`
exactly, and the tests check both (artifact checksums and 25 reference predictions).
`scikit-learn` is pinned to 1.8.0 because the pickles were created with it.

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
python -m pytest tests             # frozen ML: artifact checksums, reference predictions

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

At the time of writing: 347 backend tests, 93 ML tests and 169 frontend tests pass.

## Repository layout

| Path | What it is |
|---|---|
| `backend/app/` | FastAPI application: routes, auth, repositories (SQL), schemas, services |
| `backend/migrations/` | Numbered SQL migrations (read model, roles, auth schema) |
| `backend/scripts/migrate.py` | Migration runner (applies migrations, sets role passwords) |
| `backend/tests/` | Backend tests |
| `ml/` | Inference package for the frozen model (no Streamlit dependency) |
| `model/` | Frozen model artifacts and the training notebook |
| `tests/` | ML tests and fixtures (artifact checksums, reference predictions) |
| `frontend/` | React + TypeScript app, nginx config and its Dockerfile |
| `deploy/` | Docker helpers: database tool image, LaBSE pinning, artifact check, smoke test |
| `docker-compose.yml` | The Docker deployment |
| `pushing_into_database/` | YouTube Data API ingestion script |
| `insert_will_trend.py` | Script that wrote the training label (`will_trend`) |
| `ui/`, `predictor.py` | The original Streamlit dashboard and predictor (legacy, see below) |
| `dataset_csv_files/` | CSV exports of the trending data (Git LFS; used by the legacy dashboard) |

## Limitations

- **Data freshness is manual.** Ingestion is a script you run; the materialized views must be
  refreshed afterwards. There is no scheduler.
- **The prediction is narrow** (see above): already-trending videos only, eight countries,
  fourteen categories, 2024–2026 training data, some title signals fixed at 0. The stacking
  model receives calibrated forest scores although it was trained on uncalibrated ones; the
  model is served as-is.
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
and CI, and a properly re-evaluated (or retrained) prediction model.

## Project evolution

1. **Original project**: daily ingestion from the YouTube API into PostgreSQL, a training
   notebook (`model/final_model.ipynb`) for the stacked model, and a Streamlit dashboard
   (`ui/app.py` with `predictor.py`) that read the CSV exports.
2. **Current application**: the model was extracted unchanged into the `ml/` package, an
   analytics read model was built in PostgreSQL, a FastAPI backend and a React frontend
   replaced the Streamlit UI, accounts/workspaces/roles were added, and the stack was
   containerised.

The Streamlit dashboard (`ui/`, started with `streamlit run ui/app.py`) is kept for
reference and is no longer maintained. `predictor.py` stays because the ML tests use it as
the reference the new inference code must match.

More detail for developers: **[PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)**.
Deployment: **[DEPLOYMENT.md](DEPLOYMENT.md)**.
