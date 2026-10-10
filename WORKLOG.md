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

## 2026-10-08 — Admin access incident + dev-DB hygiene — coordinator

- Owner could not log in: their registration (`nicholas.s.tyler.4@gmail.com`, id 5)
  landed `role=user status=pending` because four smoke-test accounts registered
  first (first-account-becomes-admin rule), and the frontend has no admin-approval
  UI (scoped out of v1) — a pending account is a UI dead end.
- Fix: promoted owner account to admin+active, deleted the 4 smoke accounts and their
  albums/tags/plays via SQL. The wipe raced an in-flight agent which re-seeded
  `shelf-demo@…` (id 6, 7 classic albums) for screenshot catalog — a final cleanup
  pass after #7/#8 finishes removes ALL non-owner data from the dev DB.
- Root cause logged as **issue #9** (admin approval gap): decide between building an
  admin page or simplifying registration policy for a single-user shelf app.
- Process lesson: agents doing live smoke checks should use a scratch DB
  (`vynl_smoke`), not the owner's dev DB; note in future issue briefs.

## 2026-10-08 — Issue #7 integration — agent-integration-7

- **Shipped:** `.github/workflows/ci.yml` (reference pattern adapted: Postgres 16
  service + Python 3.12 + pip cache + `pytest` in `backend/`; Node 20 + `npm ci` +
  `npm test` + `npm run build` in `frontend/`; buildx + GHCR `latest`/`$sha` push
  on `main`, `permissions: contents: read, packages: write`, concurrency
  cancel-in-progress), `scripts/smoke.sh` (**local-only**, live provider calls),
  full `README.md` rewrite (verified quickstart, architecture + config tables,
  development/testing, troubleshooting, screenshots), `docs/screenshots/*.png` (5
  shots), `backend/Dockerfile` +`RUN mkdir -p /app/covers`, `.gitignore` +=
  `docker-compose.override.yml`.
- **Compose hardening:** `docker-compose.yml` already matched PLAN §8 (verified
  `docker compose config`); only Dockerfile covers-dir line added. Artwork
  survives recreation — verified cover bytes identical across
  `docker compose restart backend`.
- **Ports 8000/8080 occupied on this host** (unrelated `python3 -m http.server`
  + `cadvisor`) → created a **gitignored** `docker-compose.override.yml` that
  remaps **host ports only** (backend `8001:8000`, frontend `8081:80`). Compose
  here *appends* override `ports` entries, so the override uses the `!override`
  merge directive (`!reset` unsupported) to replace the committed mappings.
- **Verified live:** stack up via override (backends/nginx proxies healthy);
  smoke.sh **16/16** incl. **admin-approval path** (new user lands `pending` on a
  non-empty DB → script approves via admin `GET/PATCH /api/users`), live Deezer
  import (12 tracks), cover bytes 200 image/jpeg **direct and through nginx
  proxy**, tags replace, backdated play → dusty reason, frontend shell. CI commands
  run locally: backend `pytest` 172 passed, frontend `npm ci`/`npm test` 92
  passed/`npm run build` green. Decimal note: committed-only compose still binds
  8000/8080 (`docker compose -f docker-compose.yml config` checked).
- **Screenshots:** Playwright 1.64 headless chromium installed in a scratch dir
  under /tmp (NOT added to `frontend/package.json`, so CI `npm ci` stays lean),
  drove the real UI (login → shelf → detail → add search → find → recommend) at
  1280 px. Seeded `shelf-demo@example.com` with 7 live-imported albums + tags +
  backdated plays + a note for a realistic shelf; recommend shot filtered to a
  tag so every card shows reason + "N days since spun" badge. PNGs verified by
  element-wait + text assertions, not by eye.
- **Docs truth-checked** while writing the README: PLAN §5 still matches
  `backend/src/routers/*.py` + `frontend/src/api.ts` (no PLAN edits), and
  `.env.example` satisfies every `:?`-required compose var. Note: a literal
  `cp .env.example .env` keeps the placeholder `JWT_SECRET`, which the backend
  **refuses at startup by design** — README quickstart/troubleshooting cover it.
- **Open items for the user/coordinator:** merge to `main` then push a PR/commit
  so GitHub runs both test jobs and the GHCR `build-and-push` (no extra secrets;
  `packages: write` comes from `GITHUB_TOKEN`). Refresh screenshots after #8
  polish if UI changes meaningfully. Dev DB now holds owner + `shelf-demo`
  (7-album screenshot catalog) only — the throwaway smoke users created during
  this issue's live runs were removed after the smoke passes; per the
  coordinator's hygiene note / **issue #9**, future live smoke runs should use a
  scratch DB (`vynl_smoke`), and the screenshot catalog itself can be dropped
  once screenshots are final.

## 2026-10-08 — Issue #8 polish — agent-polish-8

- Shipped the full polish pass across all five pages + shared components +
  `styles.css`. All acceptance boxes in `docs/issues/008-polish.md` checked;
  `npm test` **95 passed** (was 92: +3 new tests, 1 extended) + `npm run build`
  green. No backend/API/type renames; no feature-logic refactors.
- **Responsive (360/768/1280):** verified/normalized breakpoints — shelf grid
  `auto-fill minmax(130px,1fr)` ≤640, detail grid stacks ≤640 (cover above
  info/tracklist), tracklist wrapped in `.tracklist-scroll` (`overflow-x` +
  table `min-width:420px` → never squashed), add/find result rows wrap ≤480
  (cover+info line, badge+button line), rec cards stack ≤640, topbar nav wraps to
  its own scrollable row ≤640. Loading skeletons mirror the real grids at every
  breakpoint.
- **Loading:** replaced text placeholders with pulse skeletons — 6-card shelf
  skeleton (`data-testid="shelf-skeleton"`) + detail skeleton
  (`detail-skeleton`); rec already had skeletons; search-as-you-type keeps stale
  results visible while “Searching…” (`role="status"`) shows.
- **Empty/error:** verified every empty state (shelf CTA, add/find no-results,
  no tags yet via TagEditor, no plays yet, rec empty + tag-filter-empty). Find
  gained per-section **Retry songs / Retry albums** (new `searchKey`; errors
  cleared on re-run; try/finally guarantees `searching` always settles → no
  infinite spinner). Add-album import failures now show a “what to try next”
  hint under the row error (`.result-hint`). 401 mid-session redirect already
  handled by `api.ts`.
- **Dark-mode audit:** every component-level hex removed — all colors live in
  `:root` theme tokens. Split `--accent` (interactive bg, pairs with new
  `--on-accent`) from `--accent-ink` (foreground links/icons — brighter warm
  orange in dark). New themed `--mb`/`--mb-border` (MusicBrainz badge).
  Computed contrast: light muted 3.63→4.92, light button text 3.31→4.58, dark
  button text 2.65→4.58, MB badge 3.66→5.31, hover 5.84. No filters/opacity on
  cover art in either theme — nothing washed out.
- **No theme flash:** inline `data-theme` script in `index.html` head runs before
  first paint (localStorage → `prefers-color-scheme` fallback), in sync with
  `theme.tsx`/`main.tsx`.
- **A11y:** uniform nav icons (Library/Plus/Search/Dices, all 15 px,
  `aria-hidden`) + `aria-label` on nav; `:focus-visible` expanded to every link
  and `.tag-chip-remove` (uses `--accent-ink`); `color: inherit` on
  `a.tag-chip-link`/`.rec-cover-link` (no stray default-blue); `aria-live
  ="polite"` on shelf grid, add results, find sections, rec grid, play history;
  `role="status"` on searching hints; Register pending/hint copy moved off inline
  styles onto token classes (`.auth-pending`/`.field-note`).
- **#6 handoff notes, each verified:** (1) nav icons — done. (2) auto-spin vs
  filter debounce — kept auto-spin-on-mount, did **not** add a debounce:
  `changeMode`/`pickTag` already invalidate in-flight requests via the request
  seq ref and land on an explicit idle prompt, so there is no request storm.
  (3) the `<`-`>` card pair never shipped in the current code (cards use labeled
  “Spun it”/“Show me another” buttons, already focus-visible). (4) tiny-shelf
  reroll repeats are now explained — a `Tiny shelf — rerolls fall back to
  repeats` note (`.rec-repeat`) appears when a reroll has to accept a card
  already on screen. (5) `.rec-*` styles audited for 640 px + dark mode.
- **Conscious deferrals (noted in issue file too):** no global fetch timeouts —
  every promise clears its spinner on settle via `finally`/`.catch`, but a
  never-resolving connection could still hang (flagged for later); rec-card
  shared-component extraction (#6’s question) left out to keep this pass
  presentation-only; shelf tag-filter with zero tags intentionally shows just the
  “All” chip (“no tags yet” copy lives in the TagEditor, where tags are made).
- **For coordinator/user:** #7’s 1280 px screenshots predate this pass — theme
  tokens, nav icons, skeleton loaders, and the tracklist wrapper change the
  visuals meaningfully, so the README screenshots should be refreshed (Playwright
  scratch setup is described in the #7 entry; not re-run here). No dev-DB changes
  made (dev-server-only check), so the post-#7/#8 cleanup plan stands.

## 2026-10-08 — README screenshot refresh (post-polish) — coordinator-helper

- **BLOCKED — no screenshots written.** The running frontend at `:8081` serves a
  **pre-#8 build**: its bundle (`/assets/index-bxiilNA3.js`) and index.html lack
  every #8 marker (`data-theme` script, `shelf-skeleton`/`detail-skeleton`,
  `tracklist-scroll`, `--accent-ink`/`--on-accent` tokens), and `vynl-frontend`
  has no volume mounts. The `vynl-frontend` image was built 2026-10-08 19:56,
  before the polished `frontend/dist` (built 20:15, `index-BGS8-iSt.js` +
  `data-theme`) — so the running container bakes in the stale #7-era UI.
  Per the brief's stop-if-stack-changed rule I did **not** rebuild/recreate the
  container or improvise a side server. Remediation: `docker compose build
  frontend && docker compose up -d frontend` (override remaps 8081→80), then the
  Playwright shot script can run as-is.
- **Everything else verified healthy for the re-run:** `/api/health` ok;
  `shelf-demo@example.com` / `ScreenshotPass123!` still admin+active with the full
  7-album catalog (ids 4–10, tags, backdated plays incl. Rumours 90d, DSOTM 60d,
  Abbey Road 30d, note on DSOTM) so the shelf/detail/recommend shots will match
  the #7 staging; live search returns MusicBrainz + Deezer rows with **no**
  `X-Search-Degraded` header (both providers up).
- **Re-run kit ready:** prior scratch at `/tmp/opencode/vynl-shots/` (Playwright
  1.64 → `chromium-1248`, driven by `shots.js`, Node at `~/.local/node`); its
  selectors match the post-#8 source except the detail wait — use `table.tracklist`
  inside `.tracklist-scroll`; recommend shot = filter tag `classic` → Spin.

## 2026-10-08 — Issue #10 palette themes — agent-palette-10

- Shipped an 8-palette theme system on a second `data-palette` axis on `<html>`
  (`default | citypop | cyberpunk | recordshop | hippie | deathmetal | punk |
  classical`), each palette a full light **and** dark token block in
  `styles.css` under `:root[data-palette='…']` and
  `:root[data-palette='…'][data-theme='dark']`; radii/spacing moved to a shared
  bare `:root`. **Default palette tokens are byte-identical to #8** (default
  ratios reproduce #8's recorded 4.58 button / 4.92 light muted / 5.31 MB /
  5.84 hover figures). Every component keeps using the same var names; the only
  component edit was `.rec-spun` switching `--accent-dark` → `--accent-ink`
  (accent-dark as text was 2.75:1 on dark surfaces — tokens untouched).
- Palettes + main light-mode accent hexes: **default** `#b85c1e` (unchanged),
  **citypop** `#4c5dd7`, **cyberpunk** `#c01a86`, **recordshop** `#b34e0e`,
  **hippie** `#bc4a2e`, **deathmetal** `#8e0f1e`, **punk** `#c81d1d`,
  **classical** `#14213d`. Dark-mode accent hexes: default `#b85c1e`, citypop
  `#6b5ce0`, cyberpunk `#c01a86`, recordshop `#b34e0e`, hippie `#bc4a2e`,
  deathmetal `#a3121f`, punk `#c81d1d`, classical `#d4a92e` (dark ink
  `#1a1e2e` on gold). Reference hexes deviated wherever white-on-neon would
  fail AA — kept the mood, see the issue Notes for the full deviation list.
- **Contrast (WCAG AA, light/dark):** every binding floor passes for all 8
  palettes × both modes — text on bg/surface ≥ 4.5 (min 11.53), muted on
  surface ≥ 4.5 (min 4.92, default light), on-accent vs accent ≥ 4.5 (min 4.58,
  worst citypop dark 4.96), MB badge ≥ 4.5 (min 4.91, citypop light),
  danger/danger-bg ≥ 4.5 (min 4.59 cyberpunk light). Only sub-4.5 value:
  default-light accent-ink/bg 4.20 (byte-identical #8 token, link/icon color,
  not in the floor). Full table in the issue Notes.
- **Settings page** `/settings`: gear icon (`Settings` lucide, `aria-label`,
  `.icon-link`) in the top bar links to it; 8-card palette grid renders live
  light+dark swatch strips from the `PALETTES` catalog (accent/bg/surface/text
  hexes, kept in sync with `styles.css` by convention), "current" badge +
  `aria-pressed`, click applies + persists instantly, `aria-live` polite;
  light/dark `mode-toggle` there too. Top-bar sun/moon toggle preserved
  (`toggleMode`). Mobile-friendly grid (auto-fill 210px → 150px ≤480).
- Storage keys: `vynl_palette` (new) alongside `vynl_theme`. `theme.tsx`
  exports `Palette`/`PaletteName`, `PALETTES` catalog, `getInitialPalette`
  (unknown value → `default`), `applyPalette`; `useTheme()` now returns
  `{ mode, palette, setMode, setPalette, toggleMode }`. `main.tsx` applies
  both axes on boot.
- **FOUC-free:** `index.html`'s pre-paint inline script now sets BOTH
  `data-theme` and `data-palette` from localStorage (validated against the
  eight ids, `default` fallback). Verified in a real Chromium (Playwright
  scratch, dev server on 5173): reload with stored `punk` + `dark` lands with
  both attributes already set and body bg = punk dark; a 16-case matrix
  checked computed styles (body/topbar/palette-card/mode-toggle/badge) against
  every palette × mode — all correct, no hardcoded colors in components.
- Tests: `theme.test.tsx` rewritten for the new API (+palette persistence /
  apply / catalog / FOUC-axis tests), `SettingsPage.test.tsx` (5: cards for all
  8, current state, click persists + applies, mode toggle, a11y labels),
  `App.test.tsx` +1 gear-link assertion. **`npm test` 108 passed** (was 95,
  +13), **`npm run build` green**. Docs: PLAN §7 paragraph + README feature
  bullet.
- For the coordinator: no backend/API changes, no new deps, no PLAN contract
  edits beyond the §7 paragraph. The docker `vynl-frontend` container on :8081
  still serves the stale #7-era build — `npm run dev` on 5173 (or a rebuild)
  is the current source of truth. Dev server was stopped after verification.

## 2026-10-08 — Issue #13 import preview — agent-preview-13

- Shipped the **dry-run import preview**: `POST /api/albums/preview` (body
  `{source, external_id}`, auth via `get_current_user` — read-only, **not**
  `require_write`). It runs the *identical* `providers.import_album` assembly (incl.
  twin discovery) and returns what import would persist, with **no DB writes and no
  dedup/409 check** — preview works even when the album is already on the shelf.
  Errors map like import: `NotFound` → 404 `"Album not found at the provider: …"`,
  other `ProviderError` → 502. The route takes **no `db` dependency** (provably
  read-only).
- **Provider layer (additive, import behavior unchanged):** `ImportedAlbum` gained
  `metadata_source`, `tracklist_source`, `artwork_source` (`str | None`) and
  `tracklists_by_source: dict[str, list[TrackInput]]`. `_assemble()` fills them:
  `metadata_source` = `"musicbrainz"` if MB present else `"deezer"` if Deezer else
  `None`; `tracklist_source` = `"deezer"` when Deezer tracks win (§6 preference)
  else `"musicbrainz"` if MB tracks else `None`; `artwork_source` = `"deezer"` if
  the Deezer cover URL was used else `"cover_art_archive"` if CAA resolved it else
  `None`; `tracklists_by_source` = each contributing source's non-empty tracklist
  (preferred always included; `.tracks` stays the preferred source's list — import
  code untouched).
- Schemas: `TrackPreviewOut`, `AlbumSourceBreakdown` (serializes identical to a
  plain dict), `AlbumPreviewOut` in `schemas.py`; `routers/albums.py` gained
  `POST /albums/preview` + `_preview_to_out()`. Breakdown fields are preview-only —
  import responses stay byte-identical.
- **Frontend:** `types.ts` `TrackPreview`/`AlbumSourceBreakdown`/`AlbumPreview`,
  `api.previewAlbum()`; new **`AlbumPreviewModal.tsx`**. Search-result **titles in
  `/add` are now buttons** (`aria-label` `Preview “{title}” by {artist}`) that open
  the modal for that row (fast-path import button kept; one modal at a time).
  Modal: `role="dialog"`/`aria-modal`/`aria-labelledby`, Esc + backdrop + close
  button, focus in on open / restored on close, body scroll locked; `CoverImage`
  (preview `cover_url`) + metadata line + `SourceBadge` + `.tracklist-scroll`-
  wrapped tracklist with `format.ts` durations; **Sources** section shows breakdown
  badges ("Metadata from MusicBrainz", … skipping null parts) and, when >1 source
  has a tracklist, a **tracklist source toggle** ("Deezer · 16 tracks" /
  "MusicBrainz · 14 tracks", preferred preselected, persists in state — the
  wrong-pressing tell); footer Cancel + Import via `api.importAlbum` with pending
  state, success → "On your shelf — view" link to `/album/{id}`, 409 → the same
  inline already-in-shelf state as AddAlbumPage (reuses `parseConflictId`, simply
  **exported** from `AddAlbumPage.tsx` — ESM cycle verified via tests + build),
  other errors inline with retry; inline preview loading + error/Retry.
- **Tests:** backend +10 in `test_albums.py` (preview == real import of the same
  ids, no row persisted, merged/MB-only/Deezer-only breakdowns, `tracklists_by_source`
  both-vs-single, tracks sorted by position, 404, 502, 422, read-only preview 200,
  no-409-when-already-on-shelf) + preview in the read-only auth sweep + breakdown
  assertions in 4 provider import tests → **182 passed** (was 172). Frontend:
  `AlbumPreviewModal.test.tsx` (7) + AddAlbumPage title-click + api `previewAlbum`
  tests → **117 passed** (was 108), `npm run build` green.
- **Docs:** PLAN §5 preview endpoint row + `AlbumPreviewOut` jsonc, §6
  source-breakdown paragraph, §7 preview modal on the Add page; README feature
  bullet. `docs/issues/013-import-preview.md` Acceptance criteria all checked,
  `Status: done`; ISSUES.md index row flipped to done.
- **Deviations from spec:** none. For #12 (more providers): preview/breakdown/
  `tracklists_by_source` are source-agnostic — only the `source` `Literal` in
  `AlbumImportRequest` needs extending when itunes/discogs land. Docker frontend on
  :8081 still serves a stale pre-#8 build; frontend checks used `npm run dev` on
  5173 (stopped after verification).

## 2026-10-08 — Issue #11 manual album entry — agent-manual-11

- Shipped **manual album entry + cover upload** (issue #11): backend
  `POST /api/albums/manual` + `PUT /api/albums/{id}/cover`, frontend
  `ManualAlbumPage` (`/add/manual`) + reusable `CoverPicker`, detail-page
  "Replace cover", `SourceBadge` manual variant, tests, docs.
- **Backend.** `schemas.py`: `ManualTrackInput {title 1..500 not-blank,
  duration_seconds? ge=0}` and `ManualAlbumInput {title*, artist*, year?, label?,
  country?, favorite?, note?, tracks?}` with validators (blank/whitespace title or
  artist → 422, year 1000…now+1). `routers/albums.py`: `create_manual_album`
  (`require_write`, 201 → AlbumOut with tracks; persists `source="manual"`,
  `external_id=uuid4().hex`, `cover_url=None`, `metadata_={}`, `track_count`
  denormalized, positions auto-assigned 1..n; soft-dedupes via
  `(user_id, lower(trim(title)), lower(trim(artist)))` → 409 reusing the existing
  `_conflict` detail `"Album already in your shelf (id=N)"`), and `upload_cover`.
  `services/artwork.py`: **`store_cover_bytes(data, album_id, *, covers_dir) ->
  str | None`** — sniffs bytes, deletes any previous `{album_id}.*` (ext may
  differ) before writing, returns filename; `None` on any failure.
- **Deviation — raw-bytes PUT (not multipart):** the issue said "(multipart,
  field `file`)" but adding `python-multipart` was out of scope; the endpoint
  takes the raw body via an async dependency `read_raw_body(request)` (route stays
  sync, matching codebase style), ignores `Content-Type`, sniffs magic bytes
  (jpeg/png/gif/webp), 400 (never 500) for empty / >15 MB `MAX_COVER_BYTES` /
  non-image payloads on any **owned** album (foreign/missing → 404 via
  `get_owned_album`). Sets `album.cover_path`, leaves `cover_url` as-is (imported
  albums keep their remote fallback). `store_cover_bytes` returns `str | None`
  (router maps `None` → 400) to preserve the module's never-raise ethos.
- **Backend tests** (appended to `test_albums.py`, reusing its fixtures): manual
  happy path (201 + track positions/count), minimal (no tracks), trim, 409
  soft-dupe, per-user isolation, read-only 403, 422 matrix (blank title/artist,
  blank track title, negative duration, year bounds + max-year-ok); cover upload
  jpeg/png with a bogus `Content-Type` (ignored), replace (old file gone), non-
  image / oversized / empty → 400, replace on an imported album, foreign + missing
  → 404, read-only 403; `store_cover_bytes` unit tests. Full suite **209 passed**
  (was 182).
- **Frontend.** `types.ts`: `ManualAlbumInput`, `ManualTrackInput`, `AlbumSource`
  += `'manual'`. `api.ts`: `createManualAlbum(input)` JSON POST;
  `uploadAlbumCover(id, blob)` raw `fetch` PUT (`Content-Type: image/jpeg` +
  Bearer, surfaces 400 detail, network error → `ApiError(0)`). New
  `components/coverNormalize.ts` (`normalizeCoverFile`: `createImageBitmap` →
  `<img>` fallback, ≤2000 px longest side, `.toBlob('image/jpeg', 0.9)` — HEIC/
  huge-photo safe) and `components/CoverPicker.tsx` ("Upload image" +
  "Take photo" `capture="environment"`, normalized preview + Remove, busy/error
  states, `onChange(blob|null)`). New `pages/ManualAlbumPage.tsx` at `/add/manual`:
  required title/artist, optional year/label/country/note, **dynamic tracklist
  editor** (add/remove rows; `parseDurationInput` handles `m:ss` or plain seconds;
  per-row + year + required-field validation), submit → create → upload cover →
  navigate `/album/{id}`; failed cover upload **keeps the album** w/ inline error +
  Retry upload + view link; 409 → existing-album link. `AlbumDetailPage`: "Replace
  cover" mounts `CoverPicker`, `saveCover()` updates in place, Cover updated.
  confirmation. `AddAlbumPage` manual-link; `SourceBadge` `manual` label.
- **Frontend tests:** `ManualAlbumPage.test.tsx` (validation, dynamic tracks,
  m:ss/ss parsing + `parseDurationInput` unit block, submit → create+upload+
  navigate, upload-failure retry, 409 link), `CoverPicker.test.tsx` (accept/
  capture attrs, normalization + blob reported, remove clears, unreadable-image
  error — `vi.mock`s `./coverNormalize`), `api.test.ts` (+4), detail-page
  replace-cover success + failed-upload (+2; hoisted api mock gained
  `uploadAlbumCover`), `SourceBadge.test.tsx` (new), AddAlbumPage manual-link.
  jsdom can't decode images, so `normalizeCoverFile` is mocked in tests and file
  inputs get their files via `Object.defineProperty` + `fireEvent.change` (hidden
  inputs, so `user.upload`'s visibility checks are bypassed). Stubbed
  `URL.createObjectURL`/`revokeObjectURL` like `CoverImage.test.tsx`. `npm test`
  **142 passed** (was 117), `npm run build` green.
- **Docs:** PLAN.md §5 (both endpoints + `ManualAlbumInput` jsonc + raw-bytes PUT
  note), §4 (`source` includes `manual`), §7 (`/add/manual` + CoverPicker +
  replace-cover + manual badge); README feature bullet;
  `docs/issues/011-manual-album-entry.md` acceptance boxes checked, Notes record
  the raw-bytes and 409-detail-string deviations, `Status: done`.
- **For the coordinator:** ISSUES.md index row for #11 was **not** touched (outside
  this issue's file scope — flip to done on commit). Docker frontend on :8081 is
  still the stale pre-#8 build; `npm run dev` on 5173 was the source of truth for
  the new route. No DB migration needed (source String(20) / external_id
  String(64)).

## 2026-10-08 — #11 cover upload switched to multipart — coordinator

- User requested the standard multipart upload instead of the agent's raw-bytes
  PUT. Added `python-multipart==0.0.32` to `backend/requirements.txt` (+ venv
  install). `PUT /api/albums/{id}/cover` now accepts a multipart `file` field
  (`UploadFile`), read with a bounded 64 kB-chunk helper that stops once
  `MAX_COVER_BYTES` is exceeded; sniff-based validation and the 400 error family
  are unchanged. Frontend `uploadAlbumCover` sends `FormData` (browser sets the
  boundary). Cover-upload tests updated to `files=` payloads; `get_owned_album`,
  `store_cover_bytes`, replace-deletes-old-ext logic all untouched.
- Verification pending: backend pytest + `npm test` + `npm run build` re-run at
  commit time.

## 2026-10-08 — Issue #12 iTunes + Discogs providers — agent-providers-12

- Shipped two new provider modules behind the existing interface:
  - `providers/itunes.py` — no key, always on. Search/lookup iterate
    `ITUNES_COUNTRIES` (default `US,JP,GB`); 0.3 s spacing floor, 20 s timeout,
    per-storefront degrade (empty result ≠ error, only all-storefront failure
    raises); artwork `100x100bb` → `600x600bb`; lookup sorts songs by
    `(discNumber, trackNumber)` for multi-disc releases.
  - `providers/discogs.py` — token-gated on `DISCOGS_TOKEN` (blank ⇒ disabled:
    direct calls raise `ProviderError("Discogs is not configured")`, merged
    search omits it). `"Artist – Title"` parse; `MM:SS`/`H:MM:SS` → seconds
    (null-safe); `spacer.gif`/`duck.gif` → no art; prefer ≥ 300 px image; 1 req/s
    floor + retry/backoff on 429 or `X-Discogs-Ratelimit-Remaining: 0`; UA
    `vynl/0.1.0 (+https://github.com/tylern4/vynl)`.
- `config.py` + `.env.example`: `discogs_token=""`, `itunes_countries="US,JP,GB"`.
- Merge generalized (`_merge.py`): `merge_results(rows: Mapping[str, list], limit)`
  keeps the original Deezer⊕MusicBrainz phase 1 byte-identical; phase 2 absorbs a
  matching iTunes row, then a matching Discogs row, into emitted rows (adds ids,
  fills year/track_count/cover only when still null — Deezer→iTunes→Discogs→MB)
  and appends unmatched rows in provider order. `merge_pair` carries all four
  ids; new `absorb_pair`; `PROVIDER_ORDER` documents the fill preference.
- `providers/__init__.py`: 4-provider concurrent fan-out (`_enabled_providers()`
  drops Discogs without a token); all-failed error only when every *enabled*
  provider fails. Import dispatch for itunes/discogs; refactored
  `_resolve_musicbrainz_twin` (+ `_find_deezer_twin`) so all four sources share
  twin discovery. `_assemble` preference: metadata MB → requested source → first
  available; tracklist/artwork Deezer → iTunes → Discogs → MusicBrainz (CAA
  last); Discogs styles/formats recorded in `metadata`.
- Schemas/router: `AlbumImportRequest.source` Literal now
  `deezer|musicbrainz|itunes|discogs` (import + preview). No DB migration —
  `itunes_id`/`discogs_id` persist in the album `metadata` JSONB; the wire
  `SearchResultOut`/`AlbumOut` deliberately don't expose them.
- Frontend: `types.ts` `AlbumSource` += `'itunes' | 'discogs'`; `SourceBadge`
  labels; `AddAlbumPage` attribution + empty state name all providers and note
  the Discogs token.
- Docs: PLAN §5/§6 (new providers, limits, token gating, preference order,
  degraded header) + README features/config table + `.env.example`.
- Tests: backend **242 passed** (was 209; +iTunes/Discogs provider, 4-provider
  merge, and preview/import endpoint tests), frontend **142 passed** (19 files),
  `npm run build` ✓. All provider HTTP is mocked — no live calls.
- Deviations: frontend `SearchResult` not extended with optional ids (nothing
  consumed them); `AlbumPreviewModal.sourceLabel()` left as-is (falls back to the
  raw provider name for iTunes/Discogs — cosmetic, out of #12 scope); iTunes
  `country` surfaced verbatim from the payload (e.g. `"USA"`, not normalized to
  the storefront code); Discogs search reads the real `label` (list of strings)
  key while also tolerating release-payload `labels` (list of dicts).

## 2026-10-08 — Deploy verification + screenshot refresh + dev-DB wipe — coordinator

- All 12 implementation issues (#1–#8, #10–#13) are done, committed, and pushed
  to `origin/main`. Rebuilt BOTH containers on the completed code (backend image
  now installs `python-multipart`; frontend bakes #8/#10/#11/#12/#13) via
  `docker compose build && up -d`; backend migrations ran clean, `/api/health` ok.
- Live smoke (`scripts/smoke.sh` with demo admin approval): **16/16 passed** —
  health, register+approve+login, 4-provider search (5 results), import, detail
  + tracklist, cover bytes direct + through nginx, tags, backdated play, dusty
  recommendation, frontend shell.
- Screenshots re-captured against the production nginx build into
  `docs/screenshots/` (shelf, album-detail, add-album, find, recommend) and
  committed. Automated verification on the built container: palette matrix
  **16/16** (8 palettes × 2 modes, computed styles), and a feature check
  (settings shows 8 palette cards + 2 modes; `/add/manual` renders form + track
  editor; clicking a result title opens the preview modal with the tracklist).
  NOTE: the coordinator model has no image input, so the PNGs were validated by
  dimensions/DOM assertions rather than by eye.
- Dev-DB wipe: deleted demo user 6 (`shelf-demo@example.com`, 7 albums) and the
  smoke user 9 (+ a leftover smoke album), with their plays/tags/album_tags and
  cached cover files. User 5 (`nicholas.s.tyler.4@gmail.com`) is the only
  remaining account, with its 3 albums/tracks/tags intact; no orphan albums and
  the covers volume now matches the DB (11/14/15).
- Tracker: issue #9 (admin-approval UI gap — pending accounts have no UI path)
  remains `open` as a known follow-up; everything else is done.

## 2026-10-09 — Issue #9 admin panel — coordinator

- Chose option (a): keep the existing invite + `pending` registration flow, but
  give admins a product path to manage accounts.
- **Backend:** new admin-only `POST /api/users` (`UserCreate`) creates an active
  user directly — the "add new users" ask — with role/status selectable, 409 on a
  duplicate email, 422 on short password / bad email; mirrors `/auth/register`.
  Existing approve/deny/role/reset/delete routes unchanged. +8 tests in
  `test_auth.py` (now 37).
- **Frontend:** new `/admin` `AdminPage` (add-user form; user table with role
  select, status pills, approve/deny, inline reset-password, delete behind an
  explicit confirm). New `AdminRoute` guard (non-admins → `/`, anonymous →
  `/login`) + an admin-only "Users" nav link. `api.ts` user-management methods,
  `types.ts` `UserCreate`, admin styles. Current admin's own row is protected
  (no deny/delete; role select disabled; "You" badge).
- **Tests:** backend **250 passed** (was 242), frontend **159 passed** (21 files;
  was 142), `npm run build` ✓. Palette-token-only styling; no DB migration.
- **Docs:** PLAN §5 (auth table + admin-UI note) and §7 (route), README features
  + setup + counts, issue #9 marked done with decision/outcome.

## 2026-10-09 — Issue #9 follow-up: move admin entry into Settings — coordinator

- Owner asked to drop the separate top-nav "Users" link and nest the admin entry
  under Settings instead.
- **Frontend:** removed the admin-only `NavLink` from `App.tsx`; added an
  admin-only **Administration** section to `SettingsPage` with a **Manage users**
  link to `/admin` (uses `useAuth`, hidden for non-admins). The `AdminRoute` guard
  and `/admin` page are unchanged, so the URL still works and is still protected.
- **Tests:** `SettingsPage.test.tsx` now mocks `useAuth` and wraps renders in a
  router; two new cases cover the admin link (href `/admin`) and its absence for
  non-admins. Frontend **161 passed** (was 159), `npm run build` ✓. No backend
  change.
- **Docs:** PLAN §5/§7 note the Settings entry; README features + setup updated.

## 2026-10-09 — Docs/quickstart/Discogs + dark-mode screenshots + vynl User-Agent — coordinator-helper

- **Deploy docs:** README gains a guided **Quick start** section
  (`scripts/quickstart.sh`) and an **Updating to the latest version** section
  (`git pull && docker compose up --build -d`, `build --pull`, logs/down, plus an
  optional GHCR prebuilt-images override). The Configuration table documents
  `ITUNES_COUNTRIES` and notes that editing `.env` needs `docker compose up -d`.
- **Discogs token:** step-by-step "Enabling Discogs (optional)" in README and
  matching steps in `.env.example`
  (<https://www.discogs.com/settings/developers>).
- **Quickstart:** `scripts/quickstart.sh` copies `.env.example` → `.env`,
  generates random `POSTGRES_PASSWORD` (48 hex) / `JWT_SECRET` (64 hex), prompts
  for invite code, MusicBrainz contact, iTunes storefronts, Discogs token and host
  ports (writes `docker-compose.override.yml` only when non-default), then offers
  to build+start. Flags `-y/--yes`, `--no-start`, `-h/--help`; a non-TTY shell
  uses defaults and does not start. Tested non-interactive and interactive (pty).
- **Outbound identity (owner request):** new `backend/src/version.py` defines
  `USER_AGENT = "vynl/0.1.0 (+https://github.com/tylern4/vynl)"`. The shared httpx
  client now sends it by default, so Deezer / iTunes / Cover Art Archive requests
  identify as vynl; MusicBrainz appends its contact (`vynl/0.1.0 (<contact>)`);
  Discogs reuses the same constant; the artwork downloader uses it too. +1
  provider test → backend **251 passed**, frontend **161 passed**.
- **Compose fix:** `docker-compose.yml` now forwards `DISCOGS_TOKEN` and
  `ITUNES_COUNTRIES` to the backend (`${DISCOGS_TOKEN:-}`,
  `${ITUNES_COUNTRIES:-US,JP,GB}`) — previously they never reached the container.
  Rebuilt + restarted the backend; `/api/health` ok and the live container reports
  the vynl User-Agent.
- **DB no longer exposed on the host (owner request):** removed the `5432:5432`
  `ports` mapping from the committed `docker-compose.yml` — the backend alone
  talks to Postgres over the internal network (`db:5432`). README and PLAN mark
  the db port as internal-only and document a local
  `docker-compose.override.yml` (`services.db.ports: ["5432:5432"]`) for host-side
  tooling; the gitignored override here will still publish it so local psql/pytest
  keep working. Base `docker compose -f docker-compose.yml config` shows no db
  port; effective local config does.
- **Screenshots (dark mode):** re-captured the five feature shots (shelf, album
  detail, add, find, recommend) in dark mode and added an eight-image theme
  gallery (`docs/screenshots/themes/*.jpg` — default, city pop, cyberpunk, record
  shop, 70s hippie, death metal, punk, classical), all linked from the README.
  Captured from a temporary `shelf-demo@example.com` shelf (12 live-imported
  albums); the demo user, its albums, plays, tags and cached covers were then
  removed.
- **Note for coordinator:** owner account 5 also holds albums 17–20 (Rumours,
  Tusk, America, COWBOY BEBOP; created 2026-10-09 ~04:36) that predate this
  session and were left untouched. Working tree is uncommitted per protocol.

## 2026-10-09 — Brand logo in the top bar (owner request) — coordinator-helper

- New `frontend/src/components/Logo.tsx`: an inline-SVG vinyl-record mark with
  the brand "V" cut into the center label. It reads the theme tokens
  (`currentColor` → `--accent-ink` for the disc, `--accent` for the label,
  `--on-accent` for the V) so the logo re-tints itself for every palette in
  light and dark mode.
- Replaces the placeholder `Disc3` lucide icon in the top-bar brand (App.tsx)
  **and** on the Login / Register auth titles; `Disc3` remains for feature
  icons (add-album empty state, "I spun this").
- New `frontend/public/vynl-logo.svg` favicon (fixed brand colors, soft tile)
  linked in `index.html`; served by Vite + nginx.
- Tests: +2 (`Logo.test.tsx`) → frontend **163 passed** (was 161), build ✓. Live
  verification on the rebuilt container: top-bar `.brand svg` resolves to the
  palette accent (e.g. citypop dark disc `#e056d6`, label `#6b5ce0`); `/vynl-logo.svg`
  → 200 `image/svg+xml`.
- README screenshots re-captured with the new logo (5 dark-mode feature shots +
  8-palette theme gallery; temp shelf user re-seeded with 12 albums — one
  MusicBrainz 503 blip retried with backoff — then cleaned up, DB back to owner
  only). README test count 163.
- **V orientation fix (owner note):** the brand V was drawn apex-up (a caret
  `^`). Corrected the `d` coordinates in both `Logo.tsx` and the favicon so the
  apex sits at the bottom (`M12 13 L16 19.4 L20 13`); added an orientation test
  asserting the apex is the lowest point → frontend **164 passed** (was 163).
  Live-verified `vPointsDown: true` on the rebuilt container and re-captured the
  README screenshots; demo seed cleaned up again.

## 2026-10-10 — Issue #14 shared shelf + open registration — coordinator

- **Shared shelf:** the collection is now one shelf for every active user, not
  per-user shelves. `albums.user_id` is attribution-only; ownership-404s removed
  from every collection route (list/detail/patch/delete/cover, plays, tag
  replace/delete, track search, recommendations). Dedupe is global — hard on
  `(source, external_id)`, soft on `(lower(title), lower(artist))` → 409
  `"Album is already on the shelf (id=N)"`. Tags are global too: `tags.user_id`
  dropped, one `name` per shelf.
- **Open registration:** the invite code now bootstraps the instance — required
  only for the very first account (the `admin`+`active` one); later signups
  register freely and land `pending` until approved (#9 admin UI). Frontend
  Register already labelled the field "Setup code (first account only)" — no
  client change.
- **Migration `0002_shared_shelf.py`:** collapses cross-user duplicate albums
  and duplicate tag names (earliest id wins; `album_tags` links repointed at the
  surviving tag before the old rows are deleted), then swaps in
  `uq_albums_source_external` / `uq_tags_name`. `alembic check` clean; verified
  on a scratch DB (upgrade 0001→0002 + drift check).
- **Test-suite fix (unrelated env leak):** with a real `DISCOGS_TOKEN` in the
  local `.env`, 8 provider tests failed because they assume Discogs is disabled
  (the CI/code default). `tests/test_providers.py` `_provider_env` now neutralizes
  ambient provider config (`discogs_token=""`, `itunes_countries="US,JP,GB"`);
  Discogs-enabled tests opt in via `_enable_discogs`.
- **Verification at commit:** backend **251 passed**, frontend **164 passed**,
  `npm run build` ✓. PLAN §4/§5/§6 + ISSUES.md updated; issue #14 marked done.
  Note: PLAN's raw-bytes-PUT cover-upload text still reflects pre-multipart #11 —
  left as a known doc drift.

## 2026-10-10 — Discogs live check added to smoke script — coordinator

- `scripts/smoke.sh` gained a live **Discogs** check (the old script only covered
  MusicBrainz/Deezer): when a `DISCOGS_TOKEN` exists in `.env`, it asserts the
  merged search's `X-Search-Degraded` header never names `discogs`, imports a
  Discogs release (a `source=="discogs"` search row when present, else the known
  id `249504` — Remain in Light) — accepting 201 or the 409 already-on-shelf
  path — and verifies the detail's tracklist resolves. Skipped automatically
  when no token is configured.
- Motivation: the unit suite covers the enabled/disabled paths with mocked HTTP,
  but the only repeatable *live* Discogs verification was manual. Confirmed the
  integration against the real API before wiring it in (search + `fetch_album`
  with the repo `.env` token both work).
- Committed alongside the #14 work; the full smoke script still runs locally only
  (never CI).
