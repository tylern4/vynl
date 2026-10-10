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

Shown in **dark mode** (each palette has a light and a dark variant).

| The shelf | Album detail | Add an album |
| --- | --- | --- |
| [![Shelf](docs/screenshots/shelf.png)](docs/screenshots/shelf.png) | [![Album detail](docs/screenshots/album-detail.png)](docs/screenshots/album-detail.png) | [![Add album](docs/screenshots/add-album.png)](docs/screenshots/add-album.png) |

| Find | Recommendations |
| --- | --- |
| [![Find](docs/screenshots/find.png)](docs/screenshots/find.png) | [![Recommend](docs/screenshots/recommend.png)](docs/screenshots/recommend.png) |

### Themes

Eight curated palettes, switchable from **Settings**. The shelf below is shown in
dark mode for each one.

| Default | City pop | Cyberpunk | Record shop |
| --- | --- | --- | --- |
| [![Default](docs/screenshots/themes/default.jpg)](docs/screenshots/themes/default.jpg) | [![City pop](docs/screenshots/themes/citypop.jpg)](docs/screenshots/themes/citypop.jpg) | [![Cyberpunk](docs/screenshots/themes/cyberpunk.jpg)](docs/screenshots/themes/cyberpunk.jpg) | [![Record shop](docs/screenshots/themes/recordshop.jpg)](docs/screenshots/themes/recordshop.jpg) |

| 70s hippie | Death metal | Punk | Classical |
| --- | --- | --- | --- |
| [![70s hippie](docs/screenshots/themes/hippie.jpg)](docs/screenshots/themes/hippie.jpg) | [![Death metal](docs/screenshots/themes/deathmetal.jpg)](docs/screenshots/themes/deathmetal.jpg) | [![Punk](docs/screenshots/themes/punk.jpg)](docs/screenshots/themes/punk.jpg) | [![Classical](docs/screenshots/themes/classical.jpg)](docs/screenshots/themes/classical.jpg) |

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
| `db`       | PostgreSQL 16 (alpine), `pg_isready` healthcheck | `vynl-db`    | — (internal only) |
| `backend`  | Python 3.14, FastAPI, SQLAlchemy 2, Alembic, uvicorn | `vynl-backend` | 8000     |
| `frontend` | React 18 + TypeScript + Vite, served by nginx (proxies `/api/` → `backend:8000`) | `vynl-frontend` | 8080 |

Postgres is deliberately **not** published on the host — only the backend talks
to it, over the internal Docker network (`db:5432`). If you need host-side
access (e.g. `psql`, or running backend tests on the host), add a local
`docker-compose.override.yml` that publishes it (see Development → Backend).

Two named volumes persist state across `compose down/up`:

- `db_data` — PostgreSQL data.
- `covers_data` — cached album artwork (`/app/covers` inside the backend).

The backend runs Alembic migrations automatically at startup and refuses to boot
with a weak `JWT_SECRET` (see Troubleshooting).

## Quick start

Requires **Docker** with the Compose plugin.

The guided script handles the fiddly parts: it copies `.env.example` → `.env`,
generates strong random `JWT_SECRET` and `POSTGRES_PASSWORD` values, prompts for
your invite code and optional settings (Discogs token, MusicBrainz contact, host
ports), then offers to build and start the stack.

```bash
git clone git@github.com:tylern4/vynl.git
cd vynl
scripts/quickstart.sh
```

Prefer to do it by hand? Same result:

```bash
git clone git@github.com:tylern4/vynl.git
cd vynl
cp .env.example .env
# edit .env: set a strong random JWT_SECRET, a private INVITE_CODE,
# and your own POSTGRES_PASSWORD
docker compose up --build -d
```

Either way, wait a few seconds for migrations, then open
[http://localhost:8080](http://localhost:8080) and register with the invite code
from `.env`. **The first account is automatically approved as admin; later
signups stay `pending` until approved.** Admins manage accounts from
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
> outbound internet access. Every request identifies itself with a
> `vynl/0.1.0` User-Agent.

### Updating to the latest version

The images are built from the source in this repo, so updating means pulling the
latest code and rebuilding. Your library lives in the named volumes (`db_data`,
`covers_data`) and survives restarts and rebuilds — and your `.env` is left
untouched.

Simplest way: the quickstart script has an update mode that keeps your current
`.env`, pulls the latest code, rebuilds the images, and recreates the stack.
It waits for the backend health check and confirms the DB is at the latest
migration head. Each step prompts first (or pass `-y` to run them all):

```bash
scripts/quickstart.sh --update        # review repo changes on pull, confirm steps
scripts/quickstart.sh --update -y     # pull + rebuild + restart non-interactively
scripts/quickstart.sh --update --no-pull --no-start   # just build, don't touch the stack
```

By hand, the same recipe:

```bash
git pull                          # or: git pull origin main
docker compose up --build -d      # rebuild changed images, restart, migrate
```

For a fully clean rebuild (also refreshes base images):

```bash
git pull
docker compose build --pull
docker compose up -d
```

> `--update` runs `git pull` automatically. If you've made local changes or want
> to review before pulling, run `git pull` yourself and add `--no-pull` (useful
> on machines where the repo isn't a git checkout either — update then just
> rebuilds and restarts).

Everyday commands:

```bash
docker compose ps                 # status + health
docker compose logs -f backend    # follow backend logs
docker compose down               # stop (keeps your data)
docker compose down -v            # stop and DELETE the volumes — destructive
```

The backend applies any new Alembic migrations automatically on startup, so no
manual DB step is needed (update mode also confirms the migration head after
restarting).

> **Prebuilt images (optional).** CI publishes images to GHCR on every push to
> `main` (`ghcr.io/tylern4/vynl/backend:latest` and `.../frontend:latest`). To run
> those instead of building locally, add to `docker-compose.override.yml`:
>
> ```yaml
> services:
>   backend:
>     image: ghcr.io/tylern4/vynl/backend:latest
>   frontend:
>     image: ghcr.io/tylern4/vynl/frontend:latest
> ```
>
> then `docker compose pull && docker compose up -d --no-build`. These packages
> are private by default, so run `docker login ghcr.io` first if you don't own
> the repo.


### Configuration

Everything is read from `.env` (copied from `.env.example`). Compose fails fast
with a clear message if a required variable is missing. After editing `.env`,
apply the change with `docker compose up -d` (it recreates the affected
containers).

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `POSTGRES_USER` | yes | `vynl` | |
| `POSTGRES_PASSWORD` | yes | `vynl` | change in production (the quickstart generates a random one) |
| `POSTGRES_DB` | yes | `vynl` | |
| `JWT_SECRET` | yes | — | used to sign auth tokens; **must be a long random string** — the backend refuses the placeholder values with a startup error |
| `INVITE_CODE` | yes | — | registration code; anyone signing up must supply it |
| `MUSICBRAINZ_CONTACT` | no | — | contact email sent with MusicBrainz requests (their policy requires a way to reach the operator) |
| `ITUNES_COUNTRIES` | no | `US,JP,GB` | comma-separated iTunes storefronts to search/look up, in fallback order (no key required) |
| `DISCOGS_TOKEN` | no | — | Discogs personal access token; **blank disables Discogs** (see below) |

#### Enabling Discogs (optional)

Discogs expands search results with a huge international catalog, but it needs a
free personal access token. Without one, Discogs is simply omitted from merged
searches and everything else keeps working.

1. Sign in at [discogs.com](https://www.discogs.com).
2. Open your developer settings: [discogs.com/settings/developers](https://www.discogs.com/settings/developers)
   (or your avatar → **Settings** → **Developers**).
3. Click **Generate new token** and copy the value.
4. Put it in `.env` as `DISCOGS_TOKEN=<your token>` and apply it:

   ```bash
   docker compose up -d backend
   ```

The quickstart script prompts for this token and links to the same page.


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

> The compose Postgres is **not** exposed on the host. To point host-side tools
> (psql, pytest) at it, first publish its port with a local override:

```yaml
# docker-compose.override.yml  (gitignored — dev-only)
services:
  db:
    ports:
      - "5432:5432"
```

```bash
docker compose up -d db      # re-read the override, recreate db
DATABASE_URL=postgresql+psycopg://vynl:vynl@localhost:5432/vynl \
JWT_SECRET=dev INVITE_CODE=dev uvicorn src.main:app --reload --port 8001

pytest          # 251 tests, uses a disposable <db>_test Postgres DB
```

> The provider tests mock HTTP — no live network. `pytest` reuses the
> `POSTGRES_*` values from the repo `.env` (falling back to `vynl`/`vynl`).

### Frontend

Node ≥ 20 (CI uses 20):

```bash
cd frontend
npm ci
npm run dev     # http://localhost:5173, proxies /api to :8000
npm test        # Vitest + React Testing Library, 164 tests
npm run build   # tsc -b && vite build
```

### CI

`.github/workflows/ci.yml` runs three jobs:

1. `backend-tests` — pytest in `backend/` against a Postgres 16 service container (Python 3.14, pip cache on `requirements-dev.txt`).
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