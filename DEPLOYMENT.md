# Deployment (Docker Compose)

```
browser ──▶ web  (nginx :8080)  ── /         → built React app (static, SPA fallback)
                                ── /api/*    → api
                                ── /health/* → api
            api  (FastAPI + frozen ML model, 1 uvicorn worker)  ──▶  db (PostgreSQL 18)
```

* **One origin** for the app and the API, so the session cookie (HttpOnly, Secure,
  SameSite=Lax, Path=/api) is first-party and no cross-site cookie/CORS setup is needed.
* Only `web` publishes a port (default `127.0.0.1:8080`). `api` and `db` are on an internal
  network: no published ports, no internet access.
* `dbtools` is a one-off tool (seed, migrations). It is the only container that ever gets the
  PostgreSQL admin password; the API gets only `yt_app_ro` (read-only analytics) and
  `yt_auth_rw` (auth schema) credentials.
* The Compose database is a **new deployment database** in the Docker volume `pgdata`. It
  never touches your local development database; you seed it once from a dump.

## Prerequisites

* Docker Desktop (or Docker Engine) with Compose v2; give it **≥ 6 GB RAM** and ~12 GB disk.
* For seeding: the local dev database `youtube_trending_db` and PostgreSQL 18 client tools
  (`pg_dump`) on the host.

## 1. Configure

```powershell
Copy-Item .env.example .env      # skip if you already have one
```

Fill in (never commit `.env`):

| Variable | Used by | Notes |
|---|---|---|
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | `db`, `dbtools` | admin of the NEW Compose database |
| `DB_APP_RO_PASSWORD` | `api`, `dbtools` | read-only analytics role `yt_app_ro` (≥ 16 chars) |
| `DB_AUTH_PASSWORD` | `api`, `dbtools` | auth role `yt_auth_rw` (≥ 16 chars) |
| `AUTH_SECRET_KEY` | `api` | ≥ 32 random chars: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `PUBLIC_ORIGIN` | `api` | URL users open, e.g. `https://trending.example.com` (default `http://localhost:8080`) |
| `WEB_BIND`, `WEB_PORT` | `web` | published address (default `127.0.0.1:8080`) |
| `API_MEM_LIMIT` | `api` | default `4g` |
| `AUTH_*` | `api` | session TTL, cookie Secure flag, registration, lockout (defaults are safe) |

`DB_HOST` is always `db` inside Compose. To keep deployment values separate from local
development values, put them in another file and pass `--env-file deploy.env` to every
`docker compose` command.

## 2. Build

```powershell
docker compose --profile tools build
```

The API image installs the pinned packages in `backend/requirements-api.lock` (CPU-only
PyTorch) and contains the exact LaBSE revision and the 8 frozen model files, each verified
against checksums during the build (`deploy/labse/labse.sha256`,
`tests/fixtures/artifact_sha256.json`); a mismatch fails the build. The first build downloads
~3 GB; later code-only changes rebuild in seconds.

## 3. Seed the database (once per new volume)

The analytics views are built from the 9 raw `public.youtube_trending_*` tables, which exist
only in the development database. Dump just those tables (read-only on the dev DB; about
170 MB, under a minute):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -h localhost -U postgres -d youtube_trending_db `
  -Fc --no-owner --no-privileges -t "public.youtube_trending_??" -f deploy/seed/raw_tables.dump
```

Then start the database and restore. `seed` refuses to run if any raw table already exists,
and restores in a single transaction:

```powershell
docker compose up -d db
docker compose run --rm dbtools seed
```

## 4. Migrate

```powershell
docker compose run --rm dbtools migrate     # apply 001–006, set role passwords, show status
docker compose run --rm dbtools status
```

Migrations never run automatically and none of them drop data. Building the two
materialized views takes a minute or two.

## 5. Start

```powershell
docker compose up -d
docker compose ps        # wait until api and web are "healthy"
```

`api` loads the ML model before it accepts requests (≈10–20 s); `web` starts once `api` is
ready. Open **http://localhost:8080**.

If port 8080 is already taken on your machine, set e.g. `WEB_PORT=8088` and
`PUBLIC_ORIGIN=http://localhost:8088` in `.env` (both together: the origin must match the URL
in the browser).

## 6. First user

Open http://localhost:8080/register and create an account. It becomes the **OWNER** of a new
workspace; add colleagues from **Team**. To close self-service sign-up afterwards, set
`AUTH_REGISTRATION_ENABLED=false` in `.env` and run `docker compose up -d api`.

## Day-to-day

| Task | Command |
|---|---|
| Logs | `docker compose logs -f api` (or `web`, `db`) |
| Stop (keeps data) | `docker compose down` |
| Restart | `docker compose up -d` |
| Rebuild after code changes | `docker compose up -d --build` |
| Smoke test (real HTTP) | `python deploy/smoke_test.py` |
| **Delete the deployment database** | `docker compose down -v` (removes `pgdata`; re-seed afterwards) |

Data lives in the named volume `yt-trending_pgdata` and survives `down`/`up` and image
rebuilds. Only `down -v` deletes it.

## Development workflow (unchanged)

Docker is not needed for development:

```powershell
python -m uvicorn app.main:app --app-dir backend --reload   # API on :8000, local dev database
cd frontend; npm run dev                                    # Vite on :5173
```

The dev frontend uses `VITE_API_BASE_URL=http://localhost:8000` (frontend/.env); the Docker
image is built with `VITE_API_BASE_URL=/` (same origin). `VITE_*` values are public: they are
compiled into the browser bundle, so never put secrets in them.

## Production considerations

* **HTTPS is required and NOT provided by this stack.** nginx here listens on plain HTTP.
  Browsers accept the Secure session cookie on `http://localhost` only. For any other host,
  put a TLS-terminating reverse proxy or load balancer (Caddy, Traefik, a cloud load
  balancer…) in front of `web`, set `PUBLIC_ORIGIN=https://your-host`, keep
  `AUTH_COOKIE_SECURE=true`, and add HSTS there. Preserve the `Host` header; the API's CSRF
  check compares `Origin` with it.
* **ML memory:** measured in the container, the API process peaks at ≈1.15 GB resident
  (LaBSE weights memory-mapped + random forest + PyTorch; cgroup-charged peak 0.74 GB). The
  model loads at startup in ≈10 s. The API runs **one** uvicorn worker on purpose: each
  worker would load its own copy and predictions are serialized by a lock anyway. Scale out
  with more `api` containers, not more workers. `API_MEM_LIMIT` defaults to `4g`; don't go
  below `2g`. The API image is ≈3.5 GB on disk (LaBSE 1.9 GB + Python packages 1.5 GB).
* **External database instead of `db`:** point `DB_HOST`/`DB_PORT` in the `api` and `dbtools`
  services at it, remove the `db` service and the `depends_on` entries, and run
  `dbtools migrate` against it. The API still needs only the two application roles.
* **Backups:** `docker compose exec db pg_dump -U <DB_USER> -Fc <DB_NAME> > backup.dump`.
* Registration is open by default (each sign-up creates its own workspace); see "First user".
