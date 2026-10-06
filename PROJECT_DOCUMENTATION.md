# Project documentation

Technical reference for people who maintain or extend YouTube Trending Intelligence.
Start with the [README](README.md) for what the project is and how to run it;
[DEPLOYMENT.md](DEPLOYMENT.md) covers the Docker deployment step by step.

Contents:

1. [System overview](#1-system-overview)
2. [Database](#2-database)
3. [Backend](#3-backend)
4. [Authentication, workspaces and RBAC](#4-authentication-workspaces-and-rbac)
5. [Analytics semantics](#5-analytics-semantics)
6. [ML inference](#6-ml-inference)
7. [Frontend](#7-frontend)
8. [API reference](#8-api-reference)
9. [Configuration](#9-configuration)
10. [Docker deployment](#10-docker-deployment)
11. [Testing](#11-testing)
12. [Design and security decisions](#12-design-and-security-decisions)
13. [Things you should not change casually](#13-things-you-should-not-change-casually)
14. [Known limitations and hardening areas](#14-known-limitations-and-hardening-areas)

---

## 1. System overview

```
                   ┌──────────────────────────── PostgreSQL ───────────────────────────────┐
 ingestion script ─▶ public.youtube_trending_{au,ca,gb,ie,in,nz,sg,us,za}   (raw, 9 tables)  │
                   │        │ migrations 002/003 (materialized views)                         │
                   │        ▼                                                                 │
                   │ app.trending_snapshots, app.video_details  ◀── SELECT ── yt_app_ro ──┐  │
                   │ auth.tenants/users/memberships/sessions    ◀── R/W ──── yt_auth_rw ─┐│  │
                   └─────────────────────────────────────────────────────────────────────┼┼──┘
                                                                                          ││
 browser ──▶ (nginx in Docker) ──▶ FastAPI app (backend/app) ─────────────────────────────┘│
                                     ├─ analytics routes → repositories (SQL) ─────────────┘
                                     ├─ auth/tenant routes → services/auth → repositories/auth
                                     └─ prediction routes → services/predictions → ml/ → model/
```

Three separate concerns share one FastAPI process:

| Concern | Code | Data | Database role |
|---|---|---|---|
| Analytics (read-only) | `api/routes/{meta,overview,analytics,videos}.py`, `repositories/` | `app.*` views | `yt_app_ro` |
| Accounts and workspaces | `api/routes/{auth,tenant}.py`, `services/auth.py`, `repositories/auth.py` | `auth.*` tables | `yt_auth_rw` |
| Predictions | `api/routes/predictions.py`, `services/predictions.py`, `ml/` | `model/trending_model_v3.joblib`, LaBSE | none |

The PostgreSQL admin credentials (`DB_USER`/`DB_PASSWORD`) are used only by the migration
runner, the ingestion and training scripts and the Docker `dbtools` container. The API never connects with
them (the engines refuse an admin user name), and in Docker it is not even given them.

### Request lifecycle

For `GET /api/v1/overview/kpis?country=IN`:

1. **Middleware** (outermost first): CORS → `RequestIdMiddleware` (assigns or reuses
   `X-Request-ID`, turns unhandled exceptions into a generic 500 envelope) →
   `OriginCheckMiddleware` (CSRF check for state-changing methods) → GZip →
   `BodySizeLimitMiddleware` (64 KB).
2. **Router dependency** `require_permission(VIEW_ANALYTICS)` → `get_current_principal`
   reads the `yt_session` cookie, HMACs it, and loads the principal (user, role, workspace)
   with a short-lived `yt_auth_rw` connection. No/expired session → 401; missing
   permission → 403.
3. **`get_db`** opens one pooled `yt_app_ro` connection for the request with
   `REPEATABLE READ`, so every query in the request sees one snapshot.
4. **`get_filters`** validates the query parameters against the data (`build_filters`).
5. The route calls a **repository** function, which runs parameterised SQL and returns
   plain dicts; Pydantic **schemas** shape the response.
6. Errors anywhere are mapped by `core/errors.py` to
   `{"error": {code, message, field, request_id, details}}` without SQL, stack traces or
   credentials.

---

## 2. Database

### Schemas and objects

| Schema | Object | Created by | Notes |
|---|---|---|---|
| `public` | `youtube_trending_<cc>` × 9 | ingestion script | Raw source data; the application only reads it through the views. Other legacy objects in `public` (e.g. `youtube_trending_all`) are not used. |
| `app` | `schema_migrations` | 001 | Applied migrations with SHA-256 checksums |
| `app` | `trending_snapshots` (materialized view) | 002 | One row per `(country_code, video_id, trending_date)`; unique index on that key plus indexes for date/country filters and per-video lookups |
| `app` | `video_details` (materialized view) | 003 | One row per `video_id`, from the video's latest snapshot across all countries, plus `first_trending_date`, `last_trending_date`, `trending_countries`, `snapshot_count` |
| `auth` | `tenants`, `users`, `memberships`, `sessions` | 005 | Accounts and workspaces (below) |
| roles | `yt_app_ro` | 004 | `SELECT` on the two views only; sessions read-only by default |
| roles | `yt_auth_rw` | 006 | `SELECT/INSERT/UPDATE` on tenants/users/memberships, `SELECT/INSERT/DELETE` on sessions; 5 s statement timeout; no access to `app` or `public` |

Both views select only the columns the application uses and exclude `will_trend` (the
training label). Category comes from the raw `video_category_id` column; empty values
become `Unknown`. Durations are converted to seconds.

**Latest-snapshot rule** (used by `video_details` and, within filters, by every
repository): most recent `trending_date`, then highest `view_count`, then alphabetically
first `country_code`.

### Migrations

- Files: `backend/migrations/NNN_name.sql`, applied in order by
  `backend/scripts/migrate.py` (requires `psql` on `PATH` or `PSQL_PATH`).
- Each migration runs in one transaction together with its `app.schema_migrations` row,
  so a failed migration leaves nothing behind.
- `migrate.py` refuses to run if an applied migration's file has changed (checksum).
- Role passwords are never in SQL files: `set-app-role-password` /
  `set-auth-role-password` send a SCRAM verifier computed client-side from `.env`.
- Commands: `status`, `apply`, `set-app-role-password`, `set-auth-role-password`.

### Refreshing data

New rows come either from the ingestion script (YouTube API, 50 videos per country per run) or
in bulk from the public Kaggle dataset `canerkonuk/youtube-trending-videos-global` (CC0, the
same YouTube API collection):

```
python pushing_into_database/import_kaggle_trending.py <youtube_trending_videos_global.parquet> [--dry-run]
```

It appends only days newer than each table's latest date, in one transaction, and never
changes existing rows. Value conventions follow the existing rows: an empty count is 0, a
hidden like/comment count (views present) is 0, and rows where YouTube returned no statistics
keep NULL counts (the model's training leaves those out). Days 2026-01-06 to 2026-10-05 were
added this way.

After ingesting new rows, refresh the views as an admin (both have unique indexes, so
`CONCURRENTLY` works and readers are not blocked):

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY app.trending_snapshots;
REFRESH MATERIALIZED VIEW CONCURRENTLY app.video_details;
```

Nothing in the application does this automatically.

### `auth` schema

| Table | Key columns | Constraints |
|---|---|---|
| `tenants` | `id uuid`, `name` | name 1–100 chars |
| `users` | `id uuid`, `email`, `display_name`, `password_hash`, `is_active`, `failed_login_count`, `locked_until`, `last_login_at` | unique lower-case email; hash must be Argon2id |
| `memberships` | `(user_id, tenant_id)`, `role` | role ∈ OWNER/ADMIN/MEMBER; `UNIQUE (user_id)` = one workspace per user |
| `sessions` | `token_hash bytea(32)`, `user_id`, `tenant_id`, `expires_at` | FK to the membership (cascade); indexed by user and expiry |

---

## 3. Backend

`backend/app/` layout:

| Module | Responsibility |
|---|---|
| `main.py` | `create_app()`: settings, middleware, exception handlers, routers, lifespan (loads the model, disposes engines) |
| `core/settings.py` | API settings from the environment (validated) |
| `core/errors.py` | Error classes and the error envelope |
| `core/middleware.py` | Request id, origin (CSRF) check, body-size limit |
| `db/config.py`, `db/engine.py`, `db/auth_engine.py` | Connection settings and the two engines (`yt_app_ro`, `yt_auth_rw`) |
| `db/health.py` | Readiness query |
| `api/deps.py` | Dependencies: DB connections, filters, principal, `require_permission` |
| `api/routes/*.py` | One router per area |
| `repositories/` | All analytics SQL (`filters`, `common`, `meta`, `overview`, `analytics`, `videos`) and auth SQL (`auth`) |
| `services/auth.py` | Registration, login, logout, members (transactions, role rules) |
| `services/predictions.py` | Model lifecycle, locking, request mapping, model description |
| `schemas/` | Pydantic request/response models (the OpenAPI contract) |
| `auth/` | Roles/permissions, password hashing, session tokens |

**Repositories.** SQL is written by hand with SQLAlchemy Core `text()`. User input only
ever appears as bound parameters; the only text formatted into SQL is the fixed filter
condition from `Filters.sql_conditions()` and identifiers from fixed whitelists (sort
columns etc.). `repositories/common.py` documents the latest-snapshot computation and the
three metric levels.

**Validation.** FastAPI/Pydantic validate types and bounds (e.g. `page_size` ≤ 100,
`limit` ≤ 50, ≤ 20 values per filter). `build_filters` validates dates against the data
range and countries/categories against values present in the database. Failures are
422 with a `field`.

**Engines.** Analytics: pool 5 + 5 overflow, `connect_timeout` 5 s, read-only sessions,
`statement_timeout` 15 s (a timeout becomes `504 query_timeout`). Auth: pool 5 + 5,
5 s statement timeout. Pool exhaustion → `503 database_busy`; connection failures →
`503 database_unavailable`.

**Health.**

- `GET /health/live` → `{"status": "ok"}`. No database access; it only shows the process
  is serving.
- `GET /health/ready` → 200 when the database answers as `yt_app_ro`, the session is
  read-only and both views are readable; otherwise 503. It also reports the ML status
  (`loaded`, `not_loaded`, `disabled`, `failed`), but the ML status does not affect
  readiness, so analytics keep working if the model fails to load.

**API docs.** `/docs`, `/redoc` and `/openapi.json` exist only when `API_DOCS_ENABLED`
is true (default: only when `APP_ENV=development`).

---

## 4. Authentication, workspaces and RBAC

### Sessions

| Step | What happens |
|---|---|
| Register | Validates input, hashes the password (Argon2id), creates a tenant, the user and an OWNER membership in one transaction, then starts a session. 409 `email_taken` if the email exists. 403 `registration_closed` if `AUTH_REGISTRATION_ENABLED=false`. |
| Login | Looks up the user by lower-cased email. Unknown email, wrong password and deactivated account all return the same 401 `invalid_credentials`. Unknown emails still run a dummy Argon2 verification, so timing does not reveal which emails exist. After `AUTH_MAX_FAILED_LOGINS` (5) consecutive failures the account is locked for `AUTH_LOCKOUT_MINUTES` (15) → 429 `too_many_attempts`. |
| Session | Token = 32 random bytes (`secrets.token_urlsafe`). Cookie `yt_session`: HttpOnly, `Secure` (configurable), `SameSite=Lax`, `Path=/api`, `Max-Age` = TTL. The database stores only `HMAC-SHA256(AUTH_SECRET_KEY, token)`. Absolute expiry `AUTH_SESSION_TTL_MINUTES` (480). |
| Each request | The principal (user, current role, workspace) is re-read from `sessions ⋈ memberships ⋈ users ⋈ tenants`, requiring an unexpired session and an active user. Role changes and deactivation therefore apply to existing sessions immediately. |
| Logout | Deletes the session row and clears the cookie. Idempotent (200 even without a session). |

Passwords: 12–128 characters, not only whitespace (same rule in the frontend for quick
feedback; the server's check is authoritative). The session token never appears in a
response body.

### Permissions

Defined in `backend/app/auth/permissions.py`:

| Role | VIEW_ANALYTICS | MAKE_PREDICTION | MANAGE_USERS |
|---|---|---|---|
| OWNER | ✓ | ✓ | ✓ |
| ADMIN | ✓ | ✓ | ✓ |
| MEMBER | ✓ | ✓ | – |

Applied in `main.py` per router: meta, overview, analytics and videos require
`VIEW_ANALYTICS`; predictions require `MAKE_PREDICTION`; `/tenant/members*` require
`MANAGE_USERS`; `/tenant` and `/auth/me` need any valid session. Health and
register/login/logout are public.

Role-management rules (`services/auth.py`, `can_assign_role`, `can_manage_member`):

- Only an OWNER can grant OWNER or change an OWNER's membership; ADMINs manage ADMINs and
  MEMBERs.
- Nobody can change their own role or active status.
- A change that would leave the workspace without an active OWNER is rejected (409
  `last_owner`). Member changes lock the tenant row, so concurrent changes cannot race.
- Deactivating a user deletes all of their sessions.

### Workspace isolation

- There is no tenant id in any URL or request body. Request models forbid unknown fields,
  so a `tenant_id` sent by a browser is rejected (422), and one in a query string is ignored.
- Every member query filters on the tenant of the authenticated session in SQL.
- A user id from another workspace is indistinguishable from an unknown id (404).
- The YouTube dataset is global and read-only; workspaces own only their users and
  memberships.

### CSRF and CORS

- `SameSite=Lax` keeps the cookie off cross-site POSTs.
- `OriginCheckMiddleware` rejects POST/PUT/PATCH/DELETE with 403 `csrf_rejected` when an
  `Origin` header is present and is neither in `CORS_ORIGINS` nor the API's own origin
  (compared with the `Host` header).
- CORS allows credentials only for the explicit `CORS_ORIGINS` list; `*` is rejected at
  startup.

---

## 5. Analytics semantics

The authoritative definitions are the docstrings and SQL in `backend/app/repositories/`
(and the `DESCRIPTION` in `main.py`, which appears in the OpenAPI docs).

**Metric levels.**

- *Snapshot-level*: one row per (country, video, day). Example: trending volume.
- *Video-level*: each video once, through its **latest snapshot within the filters**.
  Examples: unique videos, views, engagement rate.
- *Country-level*: one row per (country, video), through the latest filtered snapshot in
  that country.

**Endpoints and their metrics.**

| Endpoint | Metrics |
|---|---|
| `overview/kpis` | `unique_videos`, `trending_volume`, `views`, `unique_channels`, `engagement_rate` for the period and the previous period of equal length; `change_pct` (counts, views) and `change_pts` (engagement, percentage points). The previous period is "available" only if it starts on/after the first date in the data. |
| `overview/daily-volume` | Per day: `trending_volume` and `unique_videos` (a video trending in several selected countries that day counts once); zero-filled; optional `split_by=country|category`. No daily views, because view counts are cumulative. |
| `analytics/categories` | `trending_volume`, `volume_share_pct` (snapshot-level); `unique_videos`, `views`, `engagement_rate` (video-level; unique videos sum to the overall total). |
| `analytics/countries` | `trending_volume`; `unique_videos` (a multi-country video counts in each country); `views_of_trending_videos` = global views of those videos, **not** views from the country and **not** additive across countries; `engagement_rate`. |
| `analytics/engagement` | Totals; percentiles p25/p50/p75/p90 of per-video engagement; histogram in 1-point buckets 0–10 % plus ≥ 10 %; per-category p25/p50/p75; a views-vs-engagement scatter (top videos by views, `scatter_limit` ≤ 500). Videos with 0 views are excluded from rates and counted separately. |
| `analytics/channels` | `unique_videos`, `trending_volume`, `views`, `engagement_rate`; title and subscribers from the channel's latest filtered snapshot; sort by `unique_videos`, `trending_volume` or `views`. |
| `videos` | Per video: display fields and counts from the latest filtered snapshot; `trending_countries`, `days_on_trending` (distinct dates), first/last trending date and `snapshot_count` over all filtered snapshots. Search = case-insensitive substring of title or channel title, or an exact video id. |
| `videos/{id}` | Global latest snapshot (`app.video_details`), not filtered. |
| `videos/{id}/history` | Every snapshot of the video in every country, not filtered. |

**Formulas.** Engagement rate = `(Σ likes + Σ comments) / Σ views` over the relevant
latest snapshots (NULL if views are 0). Per-video engagement (histogram, scatter, video
list) = `(likes + comments) / views` for that snapshot.

Hidden like counts are stored as 0 in the raw data and are counted as 0.

**View counts** are YouTube's lifetime, global totals at fetch time. Summing views across
historical snapshots would count the same video many times, so the code never does it.

**Filters.** `start_date`/`end_date` must lie within the data range (default: 30 days
ending at the latest date). Repeated `country` and `category` parameters; empty means
all. Country codes are upper-cased; categories match case-insensitively. Every filtered
response echoes the filters actually applied.

---

## 6. ML inference

### Components

| Piece | Location |
|---|---|
| Inference package | `ml/` (`inference.py` – `TrendingPredictor`; `features.py` – feature construction, shared with training; `schemas.py` – inputs, validation, category/country resolution) |
| Model file | `model/trending_model_v3.joblib`: text logistic regression (with scaler), PCA (32 components), two gradient-boosting models (with and without channel numbers) and the blend weight, clip values, column order and category lists |
| Text encoder | `sentence-transformers/LaBSE`, revision `836121a0533e5664b21c7aacc5d22951f2b8b25b` (pinned in `ml/inference.py` and in the Docker image) |
| API wrapper | `backend/app/services/predictions.py` |
| Training and evaluation | `ml_training/` (`train_v3.py`, `make_reference.py`, `compare_v1.py`, `live_test.py`; report in `ml_training/REPORT.md`) |

### Pipeline (one request)

1. Validate and resolve category (name, case-insensitive, or YouTube category id) and
   country against the values in the training data. Unsupported values raise
   `InvalidInputError` → 422 `invalid_prediction_input` with per-field details.
2. **Text**: `build_text` = cleaned channel name + title + description + tags → LaBSE
   embedding (first 256 tokens) → text logistic regression = **text score**; the same
   embedding → 32 PCA components.
3. **Feature table** (`model_table`): 8 channel/duration features (log duration, log
   subscribers, log channel views, channel authority, clipped views/subscribers per video,
   legacy-channel flag, video-volume bucket) + video count, views per subscriber, short-video
   flags; title/description/tag signals (whole-word keywords, digits, `?`, `!`, lengths,
   capitals, non-Latin script, emoji, hashtags, links, tag count, "shorts", overlap);
   category and country as categoricals; the text score (as logit) and the 32 components.
4. **Gradient boosting** on that table → `high_performance_probability`.

The response contains the probability and the text score (`components.text`).

### Lifecycle

- `PredictionService` loads one `TrendingPredictor` at startup when `ML_PRELOAD=true`
  (otherwise on first use). A load failure is logged and reported as `failed`; prediction
  endpoints then return 503 `model_unavailable` while the rest of the API keeps working.
- A lock serialises loading and inference: one prediction at a time per process.
- `version` = first 12 hex digits of the model file's SHA-256, returned with each prediction.
- Nothing is stored; predictions are not logged with their inputs.
- `ML_ARTIFACT_PATH` overrides the model file location.

### Meaning

From `services/predictions.py` (the text the API returns):

- **Label**: trained only on videos already on a trending list, one row per video and country;
  high-performing in a country when, at its first trending appearance there, likes and
  comments ≥ that country's median and views ≥ 100,000 × (country median views / India median
  views); medians over all first trending appearances in each country.
- **Not a prediction of** whether an arbitrary video will reach a trending list.
- Training data: AU, CA, GB, IE, IN, NZ, US and ZA, 2024-10-12 to 2026-07-19.
- Model: 50/50 blend (average of log-odds) of two gradient-boosting models, one with and one
  without the channel numbers (`ml.features.CHANNEL_NUMBER_FEATURES`, `ml.features.blend`), so
  a wrong or extreme subscriber/view count moves a prediction about half as much.
- ROC-AUC 0.902 on the newest held-out period (2026-07-20 to 2026-10-05; previous model 0.868 on
  the same rows) and 0.851 on a live check of 398 trending videos on 2026-10-06 (previous model
  0.849 on the same videos).
- The share of high performers drifts over time, so probabilities can be off for a new period;
  ranking holds up better. Retrain periodically (`ml_training/REPORT.md`, "Retraining").

---

## 7. Frontend

Stack: React 19, TypeScript, Vite, Tailwind CSS 4, React Router 7, TanStack Query 5,
Recharts 3, Radix UI primitives, openapi-fetch with types generated by
openapi-typescript.

### Routes (`src/app/routes.tsx`)

| Path | Page | Access |
|---|---|---|
| `/login`, `/register` | Sign in / create a workspace | public (redirects away if already signed in) |
| `/` | Overview | signed in |
| `/trending` | Trending videos list | signed in |
| `/analytics` | Analytics tabs: categories, countries, engagement, channels | signed in |
| `/videos/:videoId` | Video details and history | signed in |
| `/predictions` | Prediction form, result and model card | signed in |
| `/team` | Members (shows "Access denied" without `MANAGE_USERS`) | signed in |

`RequireAuth` wraps the app shell and redirects to `/login?next=<path>` when there is no
session; `next` only accepts same-app paths. The sidebar shows only the items the user's
permissions allow. Pages are lazy-loaded.

### Data layer

- `src/api/client.ts`: typed client for `paths` from `src/api/generated/schema.ts`,
  `credentials: 'include'`, an `X-Request-ID` per request, timeouts (20 s; 30 s for
  predictions). Every failure becomes an `ApiError` with the backend's error code.
- `src/query/`: one `QueryClient`; central `queryKeys` (filters are normalised so
  `['US','IN']` and `['IN','US']` share a cache entry); stale times 60 min for filter
  metadata, 5 min for analytics, 10 min for video details, never for model info; one retry
  only for 503/504/network/timeout.
- A `401 not_authenticated` from any query or mutation marks the user signed out, and the
  route guard sends them to the sign-in page. Sign-in, registration and sign-out clear all
  cached data.
- Global filters live in the URL (`src/features/filters/`), so views can be bookmarked.

### API contract

`frontend/openapi.json` is a snapshot of the backend schema;
`src/api/generated/schema.ts` is generated from it.

```powershell
npm run api:snapshot   # fetch /openapi.json from a running backend (VITE_API_BASE_URL)
npm run api:types      # regenerate src/api/generated/schema.ts
npm run api:check      # CI-style check that the generated file is current
```

### API base URL

`VITE_API_BASE_URL` (build time, public) sets the API base URL. Unset → `http://localhost:8000`
(development). `/` → the page's own origin (the Docker image, where nginx proxies `/api`).
Never put secrets in `VITE_*` variables: they are compiled into the JavaScript bundle.

---

## 8. API reference

All paths below `/api/v1` except register, login and logout require the session cookie.

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/health/live` | public | Liveness |
| GET | `/health/ready` | public | Readiness (database) + ML status |
| POST | `/api/v1/auth/register` | public | Create account + workspace (201), signs in |
| POST | `/api/v1/auth/login` | public | Sign in |
| POST | `/api/v1/auth/logout` | public | Revoke session, clear cookie |
| GET | `/api/v1/auth/me` | session | Current user, role, permissions, workspace |
| GET | `/api/v1/tenant` | session | Current workspace (name, created, member count) |
| GET | `/api/v1/tenant/members` | MANAGE_USERS | List members |
| POST | `/api/v1/tenant/members` | MANAGE_USERS | Add a member with an initial password (201) |
| PATCH | `/api/v1/tenant/members/{user_id}` | MANAGE_USERS | Change `role` and/or `is_active` |
| GET | `/api/v1/meta/filters` | VIEW_ANALYTICS | Countries, categories, date range, default window |
| GET | `/api/v1/overview/kpis` | VIEW_ANALYTICS | KPIs with period comparison |
| GET | `/api/v1/overview/daily-volume` | VIEW_ANALYTICS | Daily series (`split_by`) |
| GET | `/api/v1/analytics/categories` | VIEW_ANALYTICS | Category performance |
| GET | `/api/v1/analytics/countries` | VIEW_ANALYTICS | Country performance |
| GET | `/api/v1/analytics/engagement` | VIEW_ANALYTICS | Engagement analysis (`scatter_limit`) |
| GET | `/api/v1/analytics/channels` | VIEW_ANALYTICS | Top channels (`sort`, `limit`) |
| GET | `/api/v1/videos` | VIEW_ANALYTICS | Video list (`sort`, `order`, `page`, `page_size`, `search`) |
| GET | `/api/v1/videos/{video_id}` | VIEW_ANALYTICS | Video detail (unfiltered) |
| GET | `/api/v1/videos/{video_id}/history` | VIEW_ANALYTICS | Full history (unfiltered) |
| GET | `/api/v1/predictions/model-info` | MAKE_PREDICTION | Model card |
| POST | `/api/v1/predictions` | MAKE_PREDICTION | Score a video |

Filter parameters on analytics/overview/videos list: `start_date`, `end_date` (ISO dates),
`country` and `category` (repeatable). Error codes you will see: `not_authenticated` (401),
`invalid_credentials` (401), `forbidden`, `csrf_rejected`, `registration_closed` (403),
`not_found` (404), `email_taken`, `last_owner` (409), `payload_too_large` (413),
`invalid_request`, `invalid_filter`, `invalid_parameter`, `invalid_prediction_input` (422),
`too_many_attempts` (429), `database_error`, `internal_error` (500), `database_unavailable`,
`database_busy`, `model_unavailable` (503), `query_timeout` (504). Every response carries
`X-Request-ID`, also repeated in error bodies as `request_id`.

---

## 9. Configuration

All configuration is environment variables, read from the process environment or `.env`
(see `.env.example`; `.env` is git-ignored).

| Variable | Default | Used by | Purpose |
|---|---|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME` | `localhost`, `5432`, – | all | Database location |
| `DB_USER`, `DB_PASSWORD` | `postgres`, – | migrations, ingestion, `ml_training`, `dbtools` | Admin account (never the API) |
| `DB_APP_RO_USER`, `DB_APP_RO_PASSWORD` | –, – | API | Read-only analytics role (`yt_app_ro`) |
| `DB_AUTH_USER`, `DB_AUTH_PASSWORD` | –, – | API | Auth role (`yt_auth_rw`) |
| `AUTH_SECRET_KEY` | – (required) | API | HMAC key for session tokens, ≥ 32 characters; the API refuses to start without it. Changing it signs everyone out. |
| `AUTH_SESSION_TTL_MINUTES` | 480 | API | Session lifetime (5–10080) |
| `AUTH_COOKIE_SECURE` | true | API | `Secure` cookie flag |
| `AUTH_REGISTRATION_ENABLED` | true | API | Allow self-service sign-up |
| `AUTH_MAX_FAILED_LOGINS`, `AUTH_LOCKOUT_MINUTES` | 5, 15 | API | Account lockout |
| `APP_ENV` | development | API | `production` disables docs by default |
| `CORS_ORIGINS` | `http://localhost:5173` | API | Comma-separated explicit origins |
| `API_DOCS_ENABLED` | dev only | API | `/docs`, `/redoc`, `/openapi.json` |
| `ML_ENABLED`, `ML_PRELOAD` | true, true | API | Serve predictions / load model at startup |
| `ML_ARTIFACT_PATH` | `model/trending_model_v3.joblib` | `ml/` | Model file override |
| `MAX_REQUEST_BYTES` | 65536 | API | Request body limit |
| `PSQL_PATH` | `psql` on PATH | `migrate.py` | psql location |
| `YOUTUBE_API_KEY` | – | ingestion script, `ml_training/live_test.py` | YouTube Data API key |
| `PUBLIC_ORIGIN`, `WEB_BIND`, `WEB_PORT`, `API_MEM_LIMIT` | see `.env.example` | Docker Compose | Deployment settings |
| `VITE_API_BASE_URL` | `http://localhost:8000` | frontend build | API base URL (public!) |

---

## 10. Docker deployment

Full instructions: [DEPLOYMENT.md](DEPLOYMENT.md). Summary of the design:

| Service | Image | Notes |
|---|---|---|
| `web` | `frontend/Dockerfile` (Node build → `nginxinc/nginx-unprivileged`) | The only published port (`127.0.0.1:8080` by default). Serves the SPA (fallback to `index.html`), proxies `/api` and `/health`. Hashed assets cached for a year, `index.html` `no-cache`, API responses `no-store`. Security headers including a Content-Security-Policy. Config: `frontend/nginx.conf`. |
| `api` | `backend/Dockerfile` | Python 3.14 slim, packages from `backend/requirements-api.lock` (CPU-only PyTorch), LaBSE pinned and checksum-verified (`deploy/labse/`), only `model/trending_model_v3.joblib`, verified against `tests/fixtures/artifact_sha256.json` at build time. Offline Hugging Face mode. One uvicorn worker, non-root (uid 10001), read-only filesystem. Health check: readiness. |
| `db` | `postgres:18-alpine` | Data in the named volume `pgdata`; not published. |
| `dbtools` | `deploy/dbtools/Dockerfile` | One-off (`--profile tools`): `seed` (restores the 9 raw tables from `deploy/seed/raw_tables.dump`, refuses if they exist), `migrate`, `status`. The only container that gets the admin password. |

Networking: `api`, `db` and `dbtools` are on an internal network with no internet access;
`web` is also on an `edge` network to publish its port. Same-origin routing means the
session cookie is first-party and the frontend is built with `VITE_API_BASE_URL=/`.

The Compose database is a **new** database: seed it from a dump of the raw tables, then
migrate. It never touches a development database. `docker compose down` keeps the data;
`down -v` deletes it.

Memory: the API process peaks at about 1.2 GB (measured), so scale with more containers
rather than more workers.

TLS is not part of the stack. For anything beyond localhost, put an HTTPS reverse proxy
in front of `web` and set `PUBLIC_ORIGIN` accordingly.

---

## 11. Testing

| Suite | Command | Needs | Covers |
|---|---|---|---|
| Backend | `python -m pytest backend/tests` | dev database with migrations applied and role passwords set; `.env` | repositories against the real data (`test_*_repository.py`), query strategy equivalence, database roles and privileges (`test_db_foundation.py`), API unit tests with mocked repositories (`api/test_api_unit.py`), API vs repository equality (`api/test_api_integration.py`), predictions through the API (`api/test_api_predictions.py`), auth/RBAC/workspace isolation/CSRF against the real database (`api/test_auth_integration.py`), auth unit tests |
| ML | `python -m pytest tests` | LaBSE in the Hugging Face cache (or internet) | the model file checksum, `ml/` never writes or fits, feature table = model columns, 25 reference predictions produced by the training pipeline, feature behaviour (`?`/`!`, whole-word keywords), input validation |
| Frontend | `npm run test:run` (in `frontend/`) | nothing external (MSW mocks the API) | routing, auth flows, protected routes, role-aware navigation, pages, filters, query keys, client and error handling |
| Static checks | `npm run lint`, `typecheck`, `format:check`, `api:check`, `build` | – | – |
| Docker smoke | `python deploy/smoke_test.py [--base URL]` | a running stack | real HTTP through nginx: headers, health, auth, analytics, the 25 reference predictions, RBAC, isolation, CSRF, logout |

Auth integration tests create accounts named `pytest-…@example.test` and delete them
afterwards (using the admin connection, in tests only).

---

## 12. Design and security decisions

- **Read model instead of raw tables.** Materialized views give the API a narrow, indexed,
  documented shape, and the raw tables are never written by the application.
- **Two least-privilege roles.** Analytics cannot write anything; auth cannot read analytics
  or raw data; neither can create objects. The admin account stays out of the API.
- **Server-side sessions, not JWTs.** Logout and deactivation take effect immediately, and
  no token is reachable from JavaScript.
- **Global data, per-workspace people.** The dataset is not copied per tenant; isolation
  applies to users and memberships.
- **One feature definition.** `ml/features.py` is used by training and serving, and the tests
  prove the app reproduces the training pipeline's predictions (the original model's training
  and serving code had drifted apart).
- **Same-origin deployment.** Avoids cross-site cookie and CORS issues.
- **Errors never leak internals.** The envelope carries a code, a user-facing message and a
  request id; details go to the server log.

---

## 13. Things you should not change casually

| Area | Why |
|---|---|
| `model/trending_model_v3.joblib` | The evaluated model; its checksum is checked by the tests and the Docker build. Saved with scikit-learn 1.8.0. Replace only via `ml_training/` (retrain, `make_reference.py`, update the checksum). |
| `ml/features.py` | Shared by training and serving; any change changes every prediction and requires retraining. |
| LaBSE revision (`deploy/labse/`) | A different revision changes the text embeddings. |
| The prediction wording (`LABEL_DEFINITION`, `NOT_A_PREDICTION_OF`) | It describes what the model can and cannot say. |
| Applied migrations (`backend/migrations/001`–`006`) | `migrate.py` refuses to run when an applied file changes. Add a new numbered migration instead. |
| `app.trending_snapshots` / `app.video_details` definitions and the latest-snapshot rule | Every metric depends on them. |
| Metric semantics in `repositories/` | Views are lifetime totals; summing snapshots or adding country views would be wrong. |
| Role grants (004, 006) and `permissions.py` | They are the authorization boundary. |
| Tenant scoping in `repositories/auth.py` / `services/auth.py` | Tenant comes from the session only. |
| Cookie flags, `OriginCheckMiddleware`, CORS settings | CSRF and session safety. |
| One worker per API container | Each worker loads its own model copy. |
| `frontend/openapi.json` | Regenerate with `api:snapshot` + `api:types` when the API changes; don't hand-edit. |

---

## 14. Known limitations and hardening areas

**Data**: manual ingestion (50 videos per country per run) and manual view refresh; tests
are tied to the current dataset.

**Model**: see section 6 (already-trending videos only, 8 countries, 15 categories, label
drift over time, 256-token text limit, no scheduled retraining).

**Authentication**: no password reset, email verification, invitations, MFA or SSO;
account lockout only (no per-IP limiting), and the lockout response reveals that an account
exists; open self-registration by default; no idle timeout or "sign out everywhere";
expired sessions are cleaned up only when that user signs in again.

**Deployment**: no TLS/HSTS in the stack; the `db` container uses the stock image settings;
images are not published and base images are pinned by tag, not digest; no automated
backups or monitoring; one API container.

**History**: an older committed version of `pushing_into_database/data_ingestion_api_v3.py`
contained a YouTube API key. That key has been deleted in Google Cloud, so the copy in git
history (which was not rewritten) no longer works. The current file reads the key from the
environment (`YOUTUBE_API_KEY` in `.env`, which is git-ignored).
