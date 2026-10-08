# vynl — Worklog

Chronological log of meaningful work. Newest entries at the **bottom**. Re-read this
file immediately before appending your entry; if it changed since you last read it,
re-read and append after the final entry.

Format: `## YYYY-MM-DD — <issue/area> — <who>` followed by short bullets: what
shipped, decisions made, anything the next agent needs to know.

---

## 2026-10-08 — Repo bootstrap — coordinator

- Initialized git repo (`main`), identity `tylern4 <nicholas.s.tyler.4@gmail.com>`.
- Committed skeleton: `.gitignore`, `.env.example`, `README.md` (project overview +
  quickstart placeholders).
- Studied [baby-tracking-app](https://github.com/tylern4/baby-tracking-app) and
  mirrored its stack: FastAPI + SQLAlchemy 2 + Alembic backend, React/Vite/TS +
  nginx frontend, PostgreSQL 16, Docker Compose, JWT auth with invite-code
  registration, pytest/Vitest suites, GHCR-pushing CI.
- Wrote [docs/PLAN.md](docs/PLAN.md): goals, data model (users, albums, tracks,
  tags, album_tags, plays), full API contract, provider strategy
  (**MusicBrainz for canonical metadata + release tracklists, Deezer for search
  relevance + track durations + cover art, Cover Art Archive for MB artwork**,
  merged/deduped on search; artwork cached to a compose volume), frontend routes,
  milestone/issue breakdown into 5 waves, and the coordination protocol.
- Decision: no `gh` CLI available → local markdown issue tracker
  ([ISSUES.md](ISSUES.md) + `docs/issues/`) instead of GitHub Issues.
- Decision: agents do not run `git` (parallel index-lock races); coordinator
  commits per issue.
- Opened issues #1–#8. Wave 1 (#1 backend foundation, #4 frontend foundation) ready
  to dispatch — disjoint directories so they can run in parallel.
