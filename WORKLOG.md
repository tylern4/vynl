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

## 2026-10-08 — Issue #4 frontend foundation — agent-frontend-1

- Shipped `frontend/`: Vite 5 + React 18 + TS scaffold (`package.json` scripts
  `dev`/`build` (`tsc -b && vite build`)/`preview`/`test`, `tsconfig.json` strict,
  `index.html`, `main.tsx`, committed `package-lock.json`), `vite.config.ts`
  (port 5173, `/api` → `http://localhost:8000` proxy, vitest jsdom +
  `src/test/setup.ts` + `css: false`).
- `src/types.ts` = the PLAN §5 contract, field-for-field: `User`/`UserAdmin`,
  `RegisterResult`, `LoginResult`, `SearchResult`, `Album` (optional `tracks?`),
  `AlbumImport`/`AlbumUpdate`/`AlbumListParams`, `Track`, `Tag` (`{id, name,
  album_count}`), `Play`, `TrackSearchResult` (+`TrackSearchAlbum`),
  `Recommendation` (+`RecommendationParams`), `AlbumSort`,
  `RecommendationMode`, `AlbumSource`. Every nullable §5 field is `| null`.
- `src/api.ts` mirrors the reference `request<T>` wrapper: `/api` prefix, JSON,
  Bearer token from localStorage key **`vynl_token`**, `ApiError(status, msg)`,
  401 → clear token + `window.location.assign('/login')` (except on
  `/auth/login`), 204 → `undefined`. **All §5 endpoints are fully implemented
  (not stubs)** — for #5/#6 the exact names are: `api.register/login/me`,
  `searchAlbums(q, limit=20)`, `importAlbum({source, external_id})`,
  `listAlbums({q,tag,favorite,sort,limit,offset})`, `getAlbum(id)`,
  `updateAlbum(id, AlbumUpdate)`, `deleteAlbum(id)`,
  **`getCoverUrl(id)` returns the URL string `/api/albums/{id}/cover` (doesn't
  fetch)**, `getTags()`, `createTag(name)`, `setAlbumTags(id, string[])`,
  `logPlay(id, playedAt?)`, `listPlays(id)`, `deletePlay(id, playId)`,
  `searchTracks(q, limit=50)`, `getRecommendations({mode,tag,n})`.
- `src/auth.tsx`: `AuthProvider` (loads `/auth/me` on mount when a token exists),
  `useAuth()` → `{user, loading, canEdit, login, register, setToken, logout}`,
  and `ProtectedRoute` (loading → "Loading…", anonymous → `<Navigate to
  "/login">`).
- Routing in `src/App.tsx`: `/login`, `/register` public; `/`, `/album/:id`,
  `/add`, `/find`, `/recommend` inside `ProtectedRoute` + an `AppShell` layout
  (top bar **vynl** + lucide `Disc3` icon, Shelf/Add/Find/Recommend nav,
  theme toggle, user name, Log out). The five feature pages are trivial
  placeholders (`src/pages/{ShelfPage,AlbumDetailPage,AddAlbumPage,FindPage,
  RecommendPage}.tsx`) that #5/#6 replace in place — route paths are final.
- `src/theme.tsx`: light/dark context, localStorage key **`vynl_theme`**, system
  preference on first visit; `styles.css` uses the reference's CSS variable names
  (`--bg/--surface/--text/--border/--accent/--muted/--danger/...`) plus
  `--radius`/`--spacing`, both themes, responsive top bar + auth pages (accent
  rebranded to warm orange).
- Production: `nginx.conf` (identical semantics: `/api/` → `backend:8000`,
  index.html no-cache, `/assets/` immutable, SPA `try_files … /index.html`) and
  multi-stage `Dockerfile` (node:20-alpine build → nginx:1.27-alpine) — matches
  the committed `docker-compose.yml` (`build: ./frontend`, 8080→80); no
  non-frontend files needed changes.
- Tests: `api.test.ts`, `App.test.tsx`, `pages/{Login,Register}.test.tsx`,
  `theme.test.tsx` + `src/test/{setup,utils}.tsx` → **25/25 passing**;
  `npm run build` green. Environment note: host had no `node`/`npm` — installed
  user-local **Node 20.18.1** from the official tarball into `~/.local/node`
  (`export PATH="$HOME/.local/node/bin:$PATH"` per shell). CI (#7) must provide
  Node ≥ 20.
- Contract notes for backend/#5: register must return `access_token: null`
  explicitly (never omit the key) for pending accounts; admin `GET/PATCH
  /api/users` from §5 are typed (`UserAdmin`) but not wrapped in `api.ts` (no
  admin route in §7). No PLAN.md changes were needed.

## 2026-10-08 — Issue #1 backend foundation — agent-backend-1

- Shipped `backend/`: pinned `requirements.txt` (fastapi 0.115.6, uvicorn,
  sqlalchemy 2.0.36, alembic, psycopg[binary], pydantic-settings,
  email-validator, bcrypt, PyJWT, **httpx 0.28.1** for #2), `requirements-dev.txt`
  (+ pytest 8.3.4), `pytest.ini`, `Dockerfile` (python:3.12-slim → uvicorn
  8000), `alembic.ini` + `alembic/` (env.py with `compare_type=True`,
  `script.py.mako`, guarded `versions/0001_initial.py`).
- `src/models.py` = **complete PLAN §4 data model**: `users` (enums
  `userrole`/`userstatus`), `albums` (unique `uq_albums_user_source_external`,
  idx on user_id/title/artist/mb_release_group/last_played_at, JSONB metadata),
  `tracks` (unique `uq_tracks_album_position`), `tags` (unique
  `uq_tags_user_name`), `album_tags` composite PK, `plays` (idx album_id +
  played_at) — all FK delete rules per §4 (albums→users SET NULL, tracks/tags
  link/plays→CASCADE, plays.user_id SET NULL). `alembic check` confirms zero
  drift between models and `0001_initial.py`.
- `src/config.py` fields: `database_url`, `jwt_secret`, `jwt_algorithm`,
  `access_token_expire_minutes`, `invite_code`, `musicbrainz_contact`,
  `covers_dir` (default `covers`), `env_file=".env"` — 1:1 with compose env.
- Auth/user surface: `src/auth.py` (bcrypt, HS256, `get_current_user`/
  `get_admin_user`/`require_write`, identical 401/403 semantics to reference),
  `routers/auth.py` (register/login/me), `routers/users.py`, auth-only
  `schemas.py`. `src/main.py` = "vynl API", lifespan (weak-JWT guard + runs
  migrations), CORS `*`, `/api` routers, `GET /api/health`.
- **Decisions other agents need:** (1) **invite code required on every
   registration** (per `.env.example` "Anyone registering must supply this") —
   wrong/missing → 403 `"Invalid invite code"`; first account is still the only
   admin+active one. Reference only checked it for the setup account; #4's
   register form should show that 403 detail for any signup. (2) Users admin:
   PLAN §5 `GET /api/users` + `PATCH /api/users/{id}` body
   `{status?, role?, password?}` (approve=`{"status":"active"}`, deny=`"denied"`)
   + `DELETE /api/users/{id}`; reference action routes
   (`POST …/approve|deny`, `PATCH …/role`, `POST …/reset-password`) also exposed
   with identical behavior via shared helpers — both contract readings work.
   Guards: last-admin demote → 400, deny/delete self → 400. (3) For #2/#3: the
   albums JSONB column is **`Album.metadata_`** (SQLAlchemy reserves `metadata`);
   DB column name is `metadata`. (4) `require_write` (for #3 write endpoints)
   403s with "Read-only account cannot make changes". (5) Lifespan rejects
   `dev-secret-change-me`/`change-me`/`change-me-in-production` as JWT_SECRET.
   (6) conftest `register_user` defaults `invite_code` to `settings.invite_code`.
- Tests: `backend/tests/conftest.py` (reference pattern: drops/recreates
  `<db>_test` per session, runs migrations, `get_db` override, TRUNCATE all six
  tables per test) + `test_auth.py` → **29 passed** locally against compose
  Postgres (`docker compose up -d db`, repo `.env` credentials, `.venv` at repo
  root). Extra verification: lifespan guard + health booted via TestClient,
  `docker build ./backend` green, and the built container served
  `/api/health` + register (first-user admin + wrong-invite 403) against the
  compose `db` — dev `vynl` DB schema dropped afterwards, left empty. Matches
  #4's typed contract (`User`/`UserAdmin`/`RegisterResult.access_token: null`).
  No PLAN.md or non-backend changes needed.

## 2026-10-08 — Issue #2 music providers — agent-providers-2

- Shipped `backend/src/providers/`: `base.py` (untouched — already sufficient:
  `SearchResult`, `ImportedAlbum`, `TrackInput`, `ProviderError(.reason)`,
  `NotFound`), `_client.py` (single HTTP seam: `get_client`/`set_client`/
  `get_json`/`url_exists` — **tests inject fakes with `set_client`**),
  `musicbrainz.py` (rg search, release import with
  `inc=recordings+artist-credits+labels+release-groups`, ms→`round(ms/1000)`,
  UA `vynl/0.1.0 ({settings.musicbrainz_contact})`, **module lock + 1.0s
  min-interval throttle**), `deezer.py` (`/search/album`, `/album/{id}`),
  `coverart.py` (HEAD-probe chain), `_merge.py` (normalize/years/merge),
  `__init__.py` (orchestration: `ThreadPoolExecutor` concurrent search, import
  assembly, twin discovery). Artwork is never downloaded — URL only.
- Public interface: committed `search_albums(query, limit=20)` and
  `import_album(source, external_id)` unchanged; `NotFound(ProviderError)` for
  404/unknown id so #3 can map 404/502.
- **⚠ CONTRACT REFINEMENT — PLAN §6 edited (two additive lines, nothing
  removed):** (1) added `search_albums_detailed(query, limit=20) ->
  SearchOutcome(results, degraded)` so §5's `X-Search-Degraded` header is
  settable — `search_albums` still returns plain `list[SearchResult]`;
  (2) added import rule 4 **"twin discovery"**: the wire body carries one id,
  so `import_album` searches the *other* provider (normalized artist+title,
  year ±1) to learn the counterpart id instead of requiring both ids. Contract
  concerns also recorded in the issue file's Notes.
- Import semantics: MB canonical (title/artist/year/label/country/rg-id) +
  Deezer tracklist/cover, each source failing independently; primary-source
  failure raises, counterpart failure degrades. `cover_url` = Deezer `cover_xl`
  → CAA `release-group/{rg}/front-500` → `release/{rel}/front` → `None`; **CAA
  404 → `cover_url=None`, not an error**.
- **Response-shape discoveries (live-verified):** MB release uses
  `label-info[]`, `media[].track-offset + track.position`, and includes
  `release-group.first-release-date`; MB invalid/unknown mbid → **400 "Invalid
  mbid."** (not 404), busy → 503. Deezer unknown album → **HTTP 200 +
  `{"error":{"code":800}}`** (unwrapped into `NotFound`). Deezer
  `/search/album` rows **omit `release_date`** → search-time `year=None` on
  Deezer rows. CAA answers HEAD 200/404 (302→archive.org) — used for probing.
- Tests: `backend/tests/test_providers.py` + 10 fixtures in
  `backend/tests/fixtures/` — **27 passed, zero live network** (all via
  `set_client` fake). Covers merged search, dedupe, one-provider-down,
  both-down, MB length normalization, Deezer-404 import fallback, NotFound,
  CAA 404→None, 1 req/s throttle, twin discovery. Provider tests shadow
  conftest's autouse `_clean_tables` with a no-op → **they need no DB**
  (verified with a dead `DATABASE_URL`); run with `POSTGRES_DB=vynl_provider`
  if the default `vynl_test` is occupied by #3. Final full-suite run at
  hand-off: **163 passed, 0 failed** (an earlier mid-hand-off run showed 6
  failures + setup errors — all transient, caused by #3's concurrent
  session/tests mid-edit; re-run after #3 settled was fully green).
- **Notes for #3:** mock seam is `providers.set_client(...)` (and
  `providers.search_albums_detailed` for the degraded header);
  `SearchOutcome.degraded` lists failing sources in order
  `("musicbrainz", "deezer")`; `ImportedAlbum` carries both
  `musicbrainz_release_group_id` and `deezer_id` (either may be `None`).
- **Notes for frontend/API:** merged search rows are `source="musicbrainz"`
  carrying `deezer_id`; MB-only rows have `cover_url=None`; Deezer-only rows
  have `year=None` — UI must render missing cover/year gracefully.
