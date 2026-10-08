# vynl

A digital bookshelf for your vinyl records. Search MusicBrainz and Deezer to import
albums, keep cover artwork and tracklists, tag your collection, find songs by mood or
vibe, and get recommendations for records you haven't spun in a while.

> **Status: pre-alpha.** The repo currently holds the plan and the issue tracker;
> implementation is tracked in [ISSUES.md](ISSUES.md). See [docs/PLAN.md](docs/PLAN.md)
> for the full technical plan and API contract.

## Features (planned)

- **Import albums** by searching MusicBrainz and Deezer side by side; results are
  merged and deduplicated.
- **Cover artwork and tracklists** — artwork is fetched from the Cover Art Archive
  (or Deezer) and cached locally; tracklists come in with song titles and lengths.
- **Tags** — label albums with moods, vibes, genres, or anything else.
- **Library search** — find albums or individual songs across your collection.
- **Recommendations** — a "dusty shelf" picker that surfaces records you haven't
  listened to in a while, plus a pure random spin of the wheel.

## Tech stack

Same shape as [baby-tracking-app](https://github.com/tylern4/baby-tracking-app):

| Service  | Tech                                   | Port  |
| -------- | -------------------------------------- | ----- |
| `db`     | PostgreSQL 16                          | 5432  |
| `backend`| Python (FastAPI + SQLAlchemy + Alembic)| 8000  |
| `frontend`| React (Vite + TypeScript) served by nginx | 8080 |

Everything runs with Docker Compose.

## First-time setup

Requires **Docker** with the Compose plugin.

```bash
git clone git@github.com:tylern4/vynl.git
cd vynl
cp .env.example .env   # then edit: set JWT_SECRET, INVITE_CODE, POSTGRES_PASSWORD
docker compose up --build -d
```

Then open [http://localhost:8080](http://localhost:8080) and register with the invite
code from `.env`. (This only works once the backend/frontend milestones land — watch
[ISSUES.md](ISSUES.md).)

## Development

Backend:

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
DATABASE_URL=postgresql+psycopg://vynl:vynl@localhost:5432/vynl \
JWT_SECRET=dev INVITE_CODE=dev uvicorn src.main:app --reload
pytest
```

Frontend:

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api to :8000
npm test
```

Database schema is managed with Alembic and applied automatically on backend startup.

## Project docs

| Document | Purpose |
| --- | --- |
| [docs/PLAN.md](docs/PLAN.md) | Detailed technical plan: data model, API contract, provider strategy |
| [ISSUES.md](ISSUES.md) | Issue tracker index (one file per issue under `docs/issues/`) |
| [WORKLOG.md](WORKLOG.md) | Chronological log of what changed and why |
