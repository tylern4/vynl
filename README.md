# vynl

A digital bookshelf for your vinyl records. Search **MusicBrainz**, **Deezer**,
and **iTunes**, add **Discogs** with a personal access token, to import albums,
keep cover artwork and full tracklists, tag your collection, find songs by mood
or vibe, and get recommendations for records you haven't spun in a while.

Built with the same stack and conventions as
[baby-tracking-app](https://github.com/tylern4/baby-tracking-app): FastAPI +
PostgreSQL + Alembic on the backend, React/TypeScript/Vite served by nginx on the
frontend, everything behind one `docker compose up`.

## Screenshots

| The shelf | Album detail | Add an album |
| --- | --- | --- |
| [![Shelf](docs/screenshots/shelf.png)](docs/screenshots/shelf.png) | [![Album detail](docs/screenshots/album-detail.png)](docs/screenshots/album-detail.png) | [![Add album](docs/screenshots/add-album.png)](docs/screenshots/add-album.png) |

| Find | Recommendations |
| --- | --- |
| [![Find](docs/screenshots/find.png)](docs/screenshots/find.png) | [![Recommend](docs/screenshots/recommend.png)](docs/screenshots/recommend.png) |

## Features

- **Import albums** by searching MusicBrainz, Deezer, and iTunes side by side —
  results are merged and deduplicated, and the artwork is cached locally. Add a
  **Discogs** token to pull releases from Discogs too (see Configuration).
- **Import preview** — click any search result to see exactly what importing it
  would create (cover, metadata, tracklist with durations, and which provider
  fed each part) before you commit, including a per-source tracklist comparison
  when more than one provider offers one.
- **Cover artwork and tracklists** — artwork from the Cover Art Archive, Deezer,
  iTunes, or Discogs is stored on a Docker volume, so it survives container
  recreation; tracklists include song titles and lengths.
- **Tags** — label records with moods, vibes, genres, or anything else, and
  filter the shelf by tag.
- **Library search** — find albums or individual songs across your collection.
- **Manual album entry** — can't find a pressing anywhere? Enter title, artist,
  year, and an optional tracklist by hand, then snap a cover with your phone camera
  or upload a file (normalized to a JPEG automatically); covers can also be replaced
  later from the album page.
- **Recommendations** — a "dusty" picker that surfaces records you haven't spun
  in a while (with a reason and "X days since spun"), plus a pure random spin.
- **Color palettes + settings** — eight curated palettes (city pop, cyberpunk,
  record shop, 70s hippie, death metal, punk, classical, and the default warm
  look), each fully styled for light and dark mode and switchable from a settings
  page.
- **User management** — admins get a `/admin` page (reachable from
  **Settings → Manage users**) to add users directly (no invite needed), list the
  accounts with roles and status, approve or deny pending signups, switch roles,
  reset passwords, and delete users.

## Architecture

| Service    | Tech                                          | Container      | Exposed port |
| ---------- | --------------------------------------------- | -------------- | ------------ |
| `db`       | PostgreSQL 16 (alpine), `pg_isready` healthcheck | `vynl-db`    | 5432         |
| `backend`  | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, uvicorn | `vynl-backend` | 8000     |
| `frontend` | React 18 + TypeScript + Vite, served by nginx (proxies `/api/` → `backend:8000`) | `vynl-frontend` | 8080 |

Two named volumes persist state across `compose down/up`:

- `db_data` — PostgreSQL data.
- `covers_data` — cached album artwork (`/app/covers` inside the backend).

The backend runs Alembic migrations automatically at startup and refuses to boot
with a weak `JWT_SECRET` (see Troubleshooting).

## First-time setup

Requires **Docker** with the Compose plugin.

```bash
git clone git@github.com:tylern4/vynl.git
cd vynl
cp .env.example .env
# edit .env: set a strong random JWT_SECRET, a private INVITE_CODE,
# and your own POSTGRES_PASSWORD
docker compose up --build -d
```

That builds and starts all three services. Wait a few seconds for migrations,
then open [http://localhost:8080](http://localhost:8080) and register with the
invite code from `.env`. **The first account is automatically approved as admin;
later signups stay `pending` until approved.** Admins manage accounts from
**Settings → Manage users** (`/admin`) — add users directly, approve/deny pending
signups, change roles, reset passwords, or delete accounts (the raw
`GET/PATCH/POST /api/users` routes back the same page).

Check it's healthy:

```bash
docker compose ps            # all three should be Up (healthy)
curl http://localhost:8080/api/health   # {"status":"ok"}
```

> Searches and imports call the **live** MusicBrainz, Deezer, iTunes, Discogs
> (when configured), and Cover Art Archive APIs, so first-time setup needs
> outbound internet access.

### Configuration

Everything is read from `.env` (copied from `.env.example`). Compose fails fast
with a clear message if a required variable is missing.

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `POSTGRES_USER` | yes | `vynl` | |
| `POSTGRES_PASSWORD` | yes | `vynl` | change in production |
| `POSTGRES_DB` | yes | `vynl` | |
| `JWT_SECRET` | yes | — | used to sign auth tokens; **must be a long random string** — the backend refuses the placeholder values with a startup error |
| `INVITE_CODE` | yes | — | registration code; anyone signing up must supply it |
| `MUSICBRAINZ_CONTACT` | no | — | contact email sent with MusicBrainz requests (their policy requires a way to reach the operator) |
| `ITUNES_COUNTRIES` | no | `US,JP,GB` | comma-separated iTunes storefronts to search/look up, in fallback order (no key required) |
| `DISCOGS_TOKEN` | no | — | Discogs personal access token (Account → Developers). **Blank disables Discogs** — it's simply omitted from merged searches |

## Smoke test

[`scripts/smoke.sh`](scripts/smoke.sh) runs a live end-to-end pass against a
running stack: health → register + login (including admin approval of a pending
user when the DB isn't empty) → external search → **real album import** → cover
bytes (direct and proxied through nginx) → tag set → play log → recommendations
→ frontend shell.

```bash
docker compose up -d
scripts/smoke.sh
#                     # custom ports / queries / creds:
# VYNL_API_URL=http://localhost:8001/api VYNL_WEB_URL=http://localhost:8081 \
# SMOKE_ADMIN_EMAIL=you@example.com SMOKE_ADMIN_PASSWORD=... scripts/smoke.sh
```

Requires `curl` and `jq`. It is **local-only by design**: it makes live
provider calls, so it is not wired into CI (CI keeps provider code mocked).

## Development

### Backend

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
```

Run against the compose database (`docker compose up -d db`), then either run
the dev server directly or inside Docker:

```bash
DATABASE_URL=postgresql+psycopg://vynl:vynl@localhost:5432/vynl \
JWT_SECRET=dev INVITE_CODE=dev uvicorn src.main:app --reload --port 8001

pytest          # 250 tests, uses a disposable <db>_test Postgres DB
```

> The provider tests mock HTTP — no live network. `pytest` reuses the
> `POSTGRES_*` values from the repo `.env` (falling back to `vynl`/`vynl`).

### Frontend

Node ≥ 20 (CI uses 20):

```bash
cd frontend
npm ci
npm run dev     # http://localhost:5173, proxies /api to :8000
npm test        # Vitest + React Testing Library, 159 tests
npm run build   # tsc -b && vite build
```

### CI

`.github/workflows/ci.yml` runs three jobs:

1. `backend-tests` — pytest in `backend/` against a Postgres 16 service container (Python 3.12, pip cache on `requirements-dev.txt`).
2. `frontend-tests` — `npm ci && npm test && npm run build` (Node 20, npm cache).
3. `build-and-push` — on pushes to `main`, builds both images with Buildx and pushes them to GHCR (`ghcr.io/<repo>/backend|frontend:latest` and `:${{ github.sha }}`).

Smoke is intentionally **not** in CI (live provider calls; see above).

## Troubleshooting

- **Ports 8000 / 8080 already in use.** The compose file binds the backend to
  `8000` and the frontend to `8080` (matching the reference project). If those
  are taken locally, create a **gitignored** `docker-compose.override.yml` that
  remaps only the *host* ports — Compose merges it automatically and containers
  still talk to each other on the internal ports:

  ```yaml
  services:
    backend:
      ports: !override
        - "8001:8000"     # host 8001 → backend 8000
    frontend:
      ports: !override
        - "8081:80"       # host 8081 → frontend 80
  ```

  (`!override` replaces the base `ports` list instead of appending to it.)

- **Backend container exits at startup: "JWT_SECRET is set to a weak default."**
  The app deliberately refuses the example placeholder secrets
  (`dev-secret-change-me`, `change-me`, `change-me-in-production`) so nobody
  ships a guessable signing key. Set a long random `JWT_SECRET` in `.env`
  (e.g. `openssl rand -hex 32`) and re-run `docker compose up -d`.

- **"JWT_SECRET must be set in .env" / "INVITE_CODE must be set in .env".**
  Compose fails fast when a required variable is missing (`${VAR:?...}`
  syntax). Copy `.env.example` → `.env` and fill it in.

- **Slow or empty searches, or a 502 on import.** MusicBrainz enforces a
  **max 1 request/second** rate limit and requires a descriptive `User-Agent`;
  vynl throttles requests to comply, so merged searches can take a beat. If one
  or more providers are down, results still come back (with the failed names in
  an `X-Search-Degraded: deezer,itunes` header); only when **every** enabled
  provider fails does the search return 502. A dedicated public IP can help if
  you're behind NAT that MusicBrainz throttles.

- **Missing artwork on some albums.** Imported albums without cover art set
  `cover_path` to null; the UI falls back to the provider's remote artwork URL,
  then to a placeholder. Albums imported from MusicBrainz alone may have no
  cover at all.

## Project docs

| Document | Purpose |
| --- | --- |
| [docs/PLAN.md](docs/PLAN.md) | Detailed technical plan: data model, full API contract, provider strategy, testing |
| [ISSUES.md](ISSUES.md) | Issue tracker index (one file per issue under `docs/issues/`) |
| [WORKLOG.md](WORKLOG.md) | Chronological log of what changed and why |

The complete **API contract** (auth, search, import, albums, tags, plays,
library search, recommendations) lives in [docs/PLAN.md §5](docs/PLAN.md).