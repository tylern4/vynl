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

## 2026-10-08 — Issue #3 collection API — agent-collection-3

- Shipped the full PLAN §5 collection surface: `routers/search.py`
  (`GET /api/search/albums`), `routers/albums.py` (import, list, detail,
  patch, delete, cover serve, plays post/get/delete), `routers/tags.py`
  (list/create, `PUT /api/albums/{id}/tags` replace, delete),
  `routers/tracks.py` (`GET /api/tracks`), `routers/recommendations.py`
  (dusty/random) — all mounted under `/api` in `main.py`. Routers import
  providers only via `from .. import providers` so tests patch
  `src.providers.{search_albums_detailed,import_album}` (no network).
- Schemas added to `src/schemas.py`: `SearchResultOut`, `AlbumImportRequest`,
  `TrackOut`, `AlbumOut` + module helper **`album_to_out(album, tracks=...)`**
  (tags sorted; `tracks=None` → `[]`, list views never load the relation),
  `AlbumUpdate`, `TagCreate/TagOut/AlbumTagsPut`, `PlayCreate/PlayOut`,
  `TrackSearchAlbum/TrackSearchOut`, `RecommendationOut` — field-for-field
  with §5 and frontend `types.ts` (verified both directions; no PLAN edits).
- Artwork lives in **`src/services/artwork.py`** (issue said services/ if it
  got heavy): streaming httpx download with 15 MB cap + magic-byte sniffing →
  `covers_dir/{album_id}.{ext}`, path-traversal-safe `resolve_cover_file`
  (bare filename, resolved inside the root), media-type map. Artwork can
  never fail an import — the module returns `None` on any error *and* the
  router guards the call defensively; failure leaves `cover_path` null (UI
  hotlinks `cover_url`).
- Semantics decisions: foreign album/tag/play → **404 (not 403)**, writes via
  #1's `require_write` → 403 `"Read-only account cannot make changes"`; import
  hard dedupe `(user_id, source, external_id)` + soft dedupe
  `lower(trim(title))|lower(trim(artist))` → 409 with
  `Album already in your shelf (id=N)`; `NotFound`→404 / `ProviderError`→502
  (catch NotFound first — it's a subclass); naive `played_at` = UTC, future >
  5 min → 422; `last_played_at` = max(played_at), recomputed (or nulled) on
  play delete (explicit `flush()` first — autoflush is off); POST tags → 201
  new / 200 existing (idempotent), everything normalized lower+trim.
- Dusty picker: candidates ordered `last_played_at ASC NULLS FIRST, id ASC`,
  pool = first `max(ceil(N*0.25), n)`, drops plays <3 days old when enough
  alternatives, jitter-ranks by `i + rng.random()*max(1, len(pool)*0.25)`
  (pool-bounded ⇒ no dupes), `n` clamped 1–20. RNG is a **FastAPI dependency
  (`get_rng`)** — tests override `app.dependency_overrides[get_rng]` with
  `random.Random(seed)` for determinism.
- `X-Search-Degraded` **is implemented** (was flagged unimplementable in the
  issue; #2 later added `search_albums_detailed → SearchOutcome` for exactly
  this). Header value is the failing provider *name* (`X-Search-Degraded:
  deezer`, comma-joined defensively), body stays a plain array; both-providers
  down still → 502.
- Contract notes for #5/#6 frontend: list `limit` default **100** (max 500) +
  `offset` — paginate explicitly for large shelves; list responses always
  carry `tracks: []` (present-but-empty, matches optional `tracks?`); success
  codes are 201 (import/play/tag-create), 200, 204 (deletes), 409 detail
  embeds the existing album id.
- Tests: `test_search.py` (external search incl. degraded header + **library
  track search**), `test_albums.py` (import/CRUD/cover incl. httpx.MockTransport
  artwork units + path traversal), `test_tags.py`, `test_plays.py`,
  `test_recommendations.py` (seeded-RNG invariants) → **172 passed, 0 failed**
  against compose Postgres. Notes: parallel pytest runs share `vynl_test` and
  `DROP … WITH (FORCE)` races were frequent mid-run — resolved by waiting for
  the other suite to finish and re-running (no conftest/DB-name changes).
  `pytest.ini` already sets `-q`, so don't add another `-q` (it suppresses the
  summary line via `-qq`).

## 2026-10-08 — Issue #5 shelf & detail UI — agent-shelf-5

- Shipped all four §7 feature pages in place (placeholders replaced): `ShelfPage`
  (responsive cover grid, instant client-side title/artist filter, server-side
  tag/favorite/sort + paging, `?tag=` deep link, empty-state CTA to `/add`),
  `AlbumDetailPage` (large cover, metadata + source badge, tracklist table with
  m:ss + total runtime footer, tag editor, "I spun this" + play history with
  delete, note editor, favorite toggle, inline-confirm remove, loading/404/error
  states), `AddAlbumPage` (300 ms debounced merged-search with source badges +
  cover thumbs, per-row import pending → "On your shelf" link, 409 → link to the
  existing album via `(id=N)` detail parsing, provider errors inline with retry,
  MB/Deezer attribution), `FindPage` (one debounced box → songs via
  `searchTracks`, albums via `listAlbums({q})`, client-filtered tags from
  `getTags` linking to `/?tag=…`). All fetches through `api.ts`, types from
  `types.ts`, no CSS framework; CSS appended to `styles.css` (new shelf/detail/
  search/chips/table section, reuses #4 variables, responsive at 640 px).
- **Filtering decision (shared components for #6/#8):** shelf text filter =
  instant client-side over a fully-paged list (`limit=500` loop until short
  page, 20-page safety cap); tag/favorite/sort = server params via refetch.
  Read-only accounts (`canEdit` false) get disabled write controls everywhere.
- Extracted shared components → `src/components/`: `AlbumCard` (title/artist·
  year, tag chips, lazy cover, star toggle; used by Shelf **and** Find),
  `CoverImage`, `SourceBadge`, `TagEditor`, plus `src/format.ts`
  (`formatDuration`, `formatRuntime`, `sumDurations`, `timeAgo`, `formatDate`).
  **#6 will likely want `AlbumCard` + `timeAgo`; #8 should audit the chip/table/
  empty-state styles and the 640 px breakpoints.**
- ⚠ **Cover-art contract note (no PLAN change):** the backend's
  `GET /api/albums/{id}/cover` is auth-gated (`get_current_user`), so a bare
  `<img>` can't load it. Added one API method — `api.getCoverBlob(id) -> Blob |
  null` (extends `api.ts`; nothing renamed) — and `CoverImage` fetches the
  cached cover through it, then falls back to `cover_url` → placeholder. Page
  test mocks ship `getCoverBlob` resolving `null`; `URL.createObjectURL` is
  stubbed only in `CoverImage.test.tsx`.
- Live smoke-tested against the real backend (compose `db` + local uvicorn on
  8123, then stopped): register (first user → admin), `/search/albums` merged
  shapes, import MB "Remain in Light" (201), listAlbums `tracks: []`, getAlbum
  tracklist, tag replace (lowercase+dedupe), logPlay/listPlays, cover → 200
  `image/jpeg`, duplicate import → 409 `Album already in your shelf (id=1)`.
  Also confirmed #2's Deezer search rows arrive with `year: None` — the add UI
  renders those gracefully. Smoke data left in the dev `vynl` DB (user +
  1 album).
- Tests: `ShelfPage.test.tsx` (10), `AlbumDetailPage.test.tsx` (11),
  `AddAlbumPage.test.tsx` (6), `FindPage.test.tsx` (4),
  `CoverImage.test.tsx` (7), `AlbumCard.test.tsx` (4), `TagEditor.test.tsx` (4),
  `format.test.ts` (4 describe blocks) → **81 passed** (`npm test`), `npm run
  build` green. New total vs #4's 25 is 81 (added 56).

## 2026-10-08 — Issue #6 recommendations UI — agent-recommend-6

- Replaced the `/recommend` placeholder with the dusty/random picker wired to
  `api.getRecommendations({mode, tag, n})`: **Dusty** (default) vs **Random**
  segmented toggle with one-line explanations, single-select mood chips from
  `getTags()` ("Any mood" + chips, `tag-chip`/`tag-filter` styles reused from
  #5), a big "Spin" button → 3-card slate. Each card reuses **`CoverImage`**
  (auth-gated blob → `cover_url` → placeholder), links through to `/album/:id`,
  and shows the API's `reason` verbatim ("Haven't spun this since Aug 2026" /
  "Never played" / "Random pick") + a `days_since_played` pill. Per-card
  **"Spun it"** → `logPlay(id)` (card swaps to the returned `AlbumOut`,
  `justSpun` state hides the stale badge, read-only accounts get a disabled
  button); **"Show me another"** refetches `n=1` with the same mode/tag and
  replaces only that slot. Loading: 3 skeleton cards (no layout jump when the
  result grid lands); empty library → CTA to `/add`; tag-filtered empty →
  "Clear tag"; error banner (backend down / 502) with Retry. Auto-spins once on
  mount (StrictMode-safe `useRef` guard) so the states are visible immediately;
  a request-sequence ref invalidates stale in-flight responses on mode/tag
  changes.
- **Decisions:** **n=3** kept (`SPIN_COUNT` const). Reroll semantics = refetch
  same params with `n: 1`; avoids landing on a card already on screen (≤5
  attempts, accepts whatever afterwards) so tiny shelves can't loop. After
  "Spun it" the card locally substitutes the logged `AlbumOut` with
  `reason: "Logged — happy spinning!"` — the backend's dusty reason would be
  stale by definition. Mode/tag change clears the slate to an "idle" prompt
  (explicit Spin applies the new selection — no auto-refetch spam). **Did not
  reuse `AlbumCard`** (rec cards have reason/badge/actions and a different
  layout) and did not extract a new shared component — flagging for #8 whether
  the rec-card layout merits extraction once the polish pass sees it.
- Nav: added lucide **`Dices`** to the top-bar Recommend link (other nav links
  stay text-only — #8 may want uniform nav icons); `.topnav a` now
  `inline-flex`. Added a small global `:focus-visible` outline block
  (`.btn`/`.icon-btn`/`.tag-chip-btn`/`.mode-toggle button`).
- No **`api.ts`/`types.ts`** changes: `getRecommendations` + `Recommendation`
  already matched the live contract, so **no PLAN.md edits**.
- Live check (port 8000 was already bound by an unrelated `python3` HTTP
  process, so I ran the built `vynl-backend:latest` one-off on **18000** on the
  `vynl_default` network, then removed it): register → flipped my smoke user to
  admin+active in the dev DB → `GET /api/recommendations` empty-library `[]`;
  imported MB "Remain in Light", tagged `chill`, verified populated dusty
  (`Never played`, `days_since_played: null`), after `logPlay` dusty returns
  `Haven't spun this since Oct 2026` / `days_since_played: 0`, random returns
  `Random pick`, `tag=chill` filters, `tag=nope → []`, bogus `mode` → 422.
  Smoke data left in dev `vynl` DB (`rec-check@example.com` + 1 album),
  same habit as #5.
- Tests: **11 new** in `RecommendPage.test.tsx` (auto-spin cards + reasons +
  badges, link-through, Random mode query, tag-in-query, Spun-it → `logPlay` +
  logged state, Show-me-another → `n: 1` swap, empty-library CTA `/add`,
  tag-empty clear, loading skeleton + disabled Spin, error/Retry, read-only
  disabled). `npm test` **92 passed** (was 81), `npm run build` green.
- **Notes for #7 (integration/docs):** the recommendations endpoint is fully
  live and matches `types.ts` — good smoke-test candidate for compose CI. `n`
  is clamped 1–20 server-side; the UI always sends 3 and rerolls use `n: 1`.
  Recommend screenshots: the rec grid with a dusty reason + badge, and the
  empty-library CTA. Port-8000 conflict note: an unrelated process holds 8000 on
  this host — compose will fail to bind until it's stopped.
- **Notes for #8 (polish):** consider uniform nav icons across Shelf/Add/Find,
  whether to keep the auto-spin-on-mount or add a filter-change debounce, the
  `<`-`>` button pair on cards (hover states are fine; focus-visible added),
  reroll duplicate-guard UX on sub-6-album shelves (≤5 attempts then accepts a
  repeat — a "nothing else left" note could explain repeats), and auditing the
  new `.rec-*` styles for the 640 px breakpoints/dark mode.
