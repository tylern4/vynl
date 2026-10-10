# vynl — Technical Plan

A digital bookshelf for your vinyl records: import albums from MusicBrainz and Deezer,
keep cover artwork and tracklists, tag records, search your library, and get
recommendations for records you haven't spun in a while.

This document is the **contract** for all implementation work. Backend and frontend
agents work in parallel against the endpoints and shapes defined here; if an
implementation needs to deviate, update this file in the same change and note it in
[WORKLOG.md](../WORKLOG.md).

---

## 1. Goals / non-goals

**Goals**

1. Add albums to a personal collection by searching one or more music metadata APIs.
2. Once imported: cover artwork + full tracklist (song titles and lengths) available.
3. User-defined tags on albums (moods, vibes, genres, whatever).
4. Search the library by song title, album, artist, or tag.
5. Recommendations: randomly surface records that haven't been listened to in a while.
6. One-command deploy with Docker Compose, same shape as baby-tracking-app.

**Non-goals (v1)**

- No audio playback or streaming integration.
- No Discogs/Spotify auth flows (both APIs need tokens; can be added later behind the
  provider interface).
- No multi-collection / wantlist split — one **shared** shelf for every approved
  user (a `wantlist` column can come later; see issue #14).
- No mobile app; the frontend is responsive and works in a phone browser.

---

## 2. Tech stack

Identical conventions to [baby-tracking-app](https://github.com/tylern4/baby-tracking-app):

| Service  | Tech                                            | Port  | Container     |
| -------- | ----------------------------------------------- | ----- | ------------- |
| `db`     | PostgreSQL 16 (alpine)                          | — (internal only) | `vynl-db`     |
| `backend`| Python 3.14, FastAPI, SQLAlchemy 2, Alembic     | 8000  | `vynl-backend`|
| `frontend`| React 18 + TypeScript + Vite, served by nginx   | 80/8080 | `vynl-frontend` |

Postgres listens only inside the compose network (`db:5432`); it is not
published on the host. For local tooling (psql, host-side pytest) publish it
with a gitignored `docker-compose.override.yml` mapping `5432` (see §7).

Key backend deps (pinned like the reference project): `fastapi`, `uvicorn`,
`sqlalchemy`, `alembic`, `psycopg[binary]`, `pydantic-settings`, `bcrypt`, `PyJWT`,
`httpx` (music provider HTTP client). Dev: `pytest`, `httpx`.

Key frontend deps: `react`, `react-dom`, `react-router-dom`, `lucide-react`; dev:
`vite`, `vitest`, `@testing-library/*`, `typescript`.

---

## 3. Repo layout

```
vynl/
├── .env.example
├── .github/workflows/ci.yml     # added in issue #7
├── docker-compose.yml
├── ISSUES.md                    # issue tracker index
├── WORKLOG.md                   # chronological work log
├── docs/
│   ├── PLAN.md                  # this file
│   ├── issues/                  # one markdown file per issue
│   └── screenshots/             # README screenshots (issue #7)
├── backend/
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/{env.py,versions/}
│   ├── requirements{,-dev}.txt
│   ├── pytest.ini
│   ├── src/
│   │   ├── main.py              # app factory, router mounting, lifespan
│   │   ├── config.py            # pydantic-settings
│   │   ├── database.py          # engine, SessionLocal, get_db
│   │   ├── migrations.py        # run_migrations() on startup
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── auth.py              # bcrypt + JWT helpers
│   │   ├── providers/           # music metadata providers (issue #2)
│   │   │   ├── __init__.py      # public interface: search_albums, import_album
│   │   │   ├── base.py          # dataclasses + provider protocol
│   │   │   ├── musicbrainz.py   # search + release lookup
│   │   │   ├── deezer.py        # search + album lookup
│   │   │   └── coverart.py      # Cover Art Archive fetch
│   │   └── routers/             # auth, search, albums, tracks, tags, recommendations
│   └── tests/                   # pytest, disposable Postgres DB
└── frontend/
    ├── Dockerfile, nginx.conf, vite.config.ts, package.json
    └── src/
        ├── api.ts               # typed fetch wrapper (same pattern as reference)
        ├── auth.tsx, theme.tsx, types.ts
        ├── pages/               # Login, Register, Shelf, AlbumDetail, AddAlbum, ...
        └── components/          # AlbumCard, TrackList, TagPicker, RecommendPanel, ...
```

---

## 4. Data model

All tables carry `created_at`/`updated_at` timestamps (`server_default=func.now()`),
mirroring the reference project's conventions.

### `users` (identical to reference)

| column | type | notes |
| --- | --- | --- |
| id | int PK | |
| email | varchar(255) unique idx | login |
| name | varchar(120) | |
| password_hash | varchar(255) | bcrypt |
| role | enum `userrole` | `admin`, `user`, `read_only` |
| status | enum `userstatus` | `pending`, `active`, `denied` |
| created_at | timestamptz | |

### `albums`

| column | type | notes |
| --- | --- | --- |
| id | int PK | |
| user_id | int FK users.id ON DELETE SET NULL, idx | attribution only — the shelf is shared (issue #14) |
| title | varchar(500) idx | album title |
| artist | varchar(500) idx | primary artist credit |
| year | int nullable | release year |
| label | varchar(255) nullable | record label |
| country | varchar(8) nullable | ISO country from source |
| source | varchar(20) | `deezer` \| `musicbrainz` \| `itunes` \| `discogs` \| `manual` (issues #11, #12) |
| external_id | varchar(64) | source id: Deezer album id or MBID |
| musicbrainz_release_group_id | varchar(36) nullable idx | set when known |
| deezer_id | bigint nullable | set when known |
| cover_path | varchar(500) nullable | relative path of cached image under COVERS_DIR |
| cover_url | varchar(1000) nullable | original remote artwork URL (for refetch) |
| track_count | int default 0 | denormalized for list views |
| favorite | bool default false | |
| note | text nullable | personal notes |
| last_played_at | timestamptz nullable idx | updated by play logging |
| metadata | JSONB default `{}` | genres, mbid extras, source payload subset |
| created_at / updated_at | timestamptz | |

Lookups are ILIKE-based in queries; unique constraint on `(source, external_id)`
prevents double import of the same release into the shared shelf (issue #14).
Cross-source dedupe happens at import time (see §6).

### `tracks`

| column | type | notes |
| --- | --- | --- |
| id | int PK | |
| album_id | int FK albums.id ON DELETE CASCADE, idx | |
| position | int | 1-based disc/track order |
| title | varchar(500) | |
| duration_seconds | int nullable | source lengths normalized to seconds |
| unique | (album_id, position) | |

### `tags`

| column | type | notes |
| --- | --- | --- |
| id | int PK | |
| name | varchar(60) | stored lowercased/trimmed |
| unique | (name) | tags are global to the shared shelf (issue #14) |

### `album_tags`

| column | type |
| --- | --- |
| album_id | int FK albums.id ON DELETE CASCADE, PK |
| tag_id | int FK tags.id ON DELETE CASCADE, PK |

### `plays`

| column | type | notes |
| --- | --- | --- |
| id | int PK | |
| album_id | int FK albums.id ON DELETE CASCADE, idx | |
| user_id | int FK users.id ON DELETE SET NULL nullable | |
| played_at | timestamptz idx | defaults to now; client may backdate |
| created_at | timestamptz | |

`albums.last_played_at` is denormalized to `max(plays.played_at)` on write so the
recommendation query stays a simple index lookup.

---

## 5. API contract

Base path `/api`, JSON everywhere, Bearer JWT auth (same `auth.py` helpers as the
reference: bcrypt hashes, HS256 tokens, `HTTPBearer`). All endpoints except
`/api/health`, register, and login require an **active** user.

### Auth — same as reference project

| Method & path | Body | Response |
| --- | --- | --- |
| `POST /api/auth/register` | `{name, email, password, invite_code?}` | `{user, access_token?}` — the **first** account becomes `admin`+`active`; the invite code is required only for that bootstrap account. Later signups register freely (no code needed) and land `pending` until approved (#9 admin flow) |
| `POST /api/auth/login` | `{email, password}` | `{access_token, token_type, user}` |
| `GET /api/auth/me` | — | `UserOut` |
| `GET /api/users` | admin only | `UserAdminOut[]` (ordered by `created_at`) |
| `POST /api/users` | admin only `{name, email, password, role="user", status="active"}` | `UserAdminOut` — direct creation for admins (#9), bypasses invite/pending; 409 on duplicate email |
| `PATCH /api/users/{id}` | admin only `{status?, role?, password?}` | `UserAdminOut` (approve/role/password) |
| `POST /api/users/{id}/approve` · `/deny` · `/reset-password` | admin only | `UserAdminOut` action routes |
| `PATCH /api/users/{id}/role` | admin only `{role}` | `UserAdminOut` |
| `DELETE /api/users/{id}` | admin only | `204` (self-delete blocked) |

**Admin UI (#9).** The frontend exposes an admin-only `/admin` page, reached from
a **Manage users** entry in Settings (shown to `role=admin` only); `AdminRoute`
redirects non-admins to `/` and anonymous visitors to `/login`. It can add a user,
list users with role/status, approve/deny, switch role, reset password, and delete.
The current admin's own row is protected (no deny/delete, role select disabled).

### External search (for the "add album" flow)

| Method & path | Query | Response |
| --- | --- | --- |
| `GET /api/search/albums` | `q` (required), `limit=20` | `SearchResult[]` |

```jsonc
// SearchResult
{
  "source": "deezer",              // "deezer" | "musicbrainz" | "itunes" | "discogs"
  "external_id": "302127",         // Deezer album id or MusicBrainz release-group MBID
  "title": "Remain in Light",
  "artist": "Talking Heads",
  "year": 1980,                    // nullable
  "track_count": 8,                // nullable if source doesn't say
  "cover_url": "https://...",      // nullable; preview artwork
  "label": "Sire"                  // nullable
}
```

Results from every enabled provider are fetched, normalized, and
**deduplicated** by `(lower(artist), lower(title), year ± 1)` — merged rows prefer
Deezer's `cover_url`/`track_count` and MusicBrainz's `year`/`label` when both
exist, absorbing a matching iTunes (then Discogs) row without reordering the
Deezer/MusicBrainz pairing (merged row keeps every id in a `sources` detail; see
§6). Endpoint tolerates one provider being down: returns the others' results with
the failed provider names in headers (`X-Search-Degraded: deezer,itunes`) —
response body stays a plain array. Discogs is **omitted entirely** unless a
token is configured (§6), so it never appears as degraded on an unconfigured
install.

### Import & collection

| Method & path | Body | Response |
| --- | --- | --- |
| `POST /api/albums/import` | `{source, external_id}` | `AlbumOut` (201; **409** if the release is already on the shared shelf) |
| `POST /api/albums/manual` | `ManualAlbumInput` | `AlbumOut` (201; **409** on soft-dupe, **422** on invalid fields; issue #11) |
| `POST /api/albums/preview` | `{source, external_id}` | `AlbumPreviewOut` — a **dry-run** of import: same assembly code path (incl. twin discovery), but **no album row is created and no 409 is raised** (works for albums already on the shelf); `NotFound` → 404, other provider errors → 502, exactly like import (issue #13) |
| `GET /api/albums` | `q`, `tag`, `favorite`, `sort` (`added`\|`title`\|`artist`\|`year`\|`played`), `limit`, `offset` | `AlbumOut[]` (without tracks) |
| `GET /api/albums/{id}` | — | `AlbumOut` **with `tracks[]`** |
| `PATCH /api/albums/{id}` | `{favorite?, note?, year?, label?}` | `AlbumOut` |
| `DELETE /api/albums/{id}` | — | `204` |
| `GET /api/albums/{id}/cover` | — | image bytes (`image/jpeg`/`png`/`webp`), `Cache-Control: public, max-age=86400`; `404` if never fetched, frontend falls back to `cover_url` |
| `PUT /api/albums/{id}/cover` | **raw image bytes** (issue #11) | `AlbumOut` — sets `cover_path`; 400 on empty/oversized/non-image payload; `cover_url` left as-is |

```jsonc
// ManualAlbumInput — POST /api/albums/manual (issue #11; no provider involved)
{
  "title": "Midnight Crush",          // required (trimmed, 1..500)
  "artist": "Tokyo Heartbeat",        // required (trimmed, 1..500)
  "year": 1983, "label": "...", "country": "JP",   // optional
  "favorite": false, "note": "...",                 // optional
  "tracks": [                        // optional; positions auto-assigned 1..n
    {"title": "Track One", "duration_seconds": 214} // title required, duration optional (>= 0)
  ]
}
```

The manual album persists `source="manual"` with `external_id` = a fresh
`uuid4().hex` (satisfies the global `(source, external_id)` unique constraint),
`cover_url`/`cover_path` null until the user uploads art, and `metadata_={}`.
Creation soft-dedupes exactly like import —
`(lower(trim(title)), lower(trim(artist)))` already on the shelf → **409**
`"Album is already on the shelf (id=N)"`. Validation is 422: blank/whitespace
title/artist, blank track title, negative `duration_seconds`, year outside
1000…now+1.

**Cover upload is a raw-bytes PUT** — a deliberate deviation from the issue's
multipart wording: the `Content-Type` header is ignored and the payload is sniffed
by magic bytes (`services.artwork.sniff_image`), so `python-multipart` is never
needed. The frontend normalizes the pick to a ≤ ~2000 px JPEG (HEIC-safe) before
uploading; the backend replaces any previously stored `{album_id}.*` file (extension
may differ) and returns 400 — never 500 — for empty / > 15 MB / non-image bytes. Works
for any album on the shared shelf (manual or imported).

```jsonc
// AlbumOut (list variant: tracks omitted or empty)
{
  "id": 1,
  "title": "Remain in Light",
  "artist": "Talking Heads",
  "year": 1980,
  "label": "Sire",
  "country": "US",
  "source": "musicbrainz",
  "external_id": "…mbid…",
  "cover_url": "https://…",        // remote original; frontend uses /api/albums/{id}/cover first
  "track_count": 8,
  "favorite": false,
  "note": null,
  "last_played_at": "2026-08-01T22:14:00Z",   // nullable
  "tags": ["art-rock", "summer"],
  "created_at": "…",
  "tracks": [                      // only on GET /api/albums/{id}
    {"id": 10, "position": 1, "title": "Born Under Punches", "duration_seconds": 349}
  ]
}
```

```jsonc
// AlbumPreviewOut — POST /api/albums/preview (dry-run; issue #13)
{
  "source": "musicbrainz",
  "external_id": "…mbid…",
  "title": "Remain in Light",
  "artist": "Talking Heads",
  "year": 1980,
  "label": "Sire",
  "country": "US",
  "cover_url": "https://…",
  "track_count": 8,
  "tracks": [{"position": 1, "title": "Born Under Punches", "duration_seconds": 349}],
  "source_breakdown": {            // which provider fed each part (all nullable)
    "metadata_source": "musicbrainz",
    "tracklist_source": "deezer",
    "artwork_source": "deezer"
  },
  "tracklists_by_source": {        // each contributing source's tracklist
    "deezer": [{"position": 1, "title": "Born Under Punches", "duration_seconds": 349}],
    "musicbrainz": [{"position": 1, "title": "Born Under Punches", "duration_seconds": 344}]
  }
}
```

### Tags

| Method & path | Body | Response |
| --- | --- | --- |
| `GET /api/tags` | — | `[{id, name, album_count}]` (own tags only) |
| `POST /api/tags` | `{name}` | `TagOut` (idempotent: existing name returns it) |
| `PUT /api/albums/{id}/tags` | `{tags: ["chill", "vinyl-33"]}` | `AlbumOut` — **replaces** the tag set, creating missing tags |
| `DELETE /api/tags/{id}` | — | `204` (removes tag everywhere) |

### Plays (listen logging)

| Method & path | Body | Response |
| --- | --- | --- |
| `POST /api/albums/{id}/plays` | `{played_at?}` (ISO datetime, default now) | `AlbumOut` (updates `last_played_at`) |
| `GET /api/albums/{id}/plays` | — | `[{id, played_at}]` newest first |
| `DELETE /api/albums/{id}/plays/{play_id}` | — | `204` (recomputes `last_played_at`) |

### Library song search

| Method & path | Query | Response |
| --- | --- | --- |
| `GET /api/tracks` | `q` (required), `limit=50` | `TrackSearchOut[]` |

```jsonc
{
  "id": 10,
  "title": "Once in a Lifetime",
  "duration_seconds": 259,
  "position": 6,
  "album": {"id": 1, "title": "Remain in Light", "artist": "Talking Heads",
             "year": 1980, "cover_url": "https://…"}
}
```

Matched with ILIKE across `tracks.title`, `albums.title`, `albums.artist` for the
current user, ordered by artist/title/position.

### Recommendations

| Method & path | Query | Response |
| --- | --- | --- |
| `GET /api/recommendations` | `mode=dusty`\|`random` (default `dusty`), `tag`, `n=1` (1–20) | `RecommendationOut[]` |

```jsonc
{
  "album": { /* AlbumOut, no tracks */ },
  "reason": "Haven't spun this since Aug 2026",  // or "Never played" / "Random pick"
  "days_since_played": 68                        // null if never played
}
```

**`dusty` algorithm:** candidate set = user's albums (optionally by tag), ranked by
`COALESCE(last_played_at, '-infinity')` ascending; sample `n` **without replacement**
from the bottom 25% of the ranking using random jitter so the answer isn't always the
same record, skipping anything played in the last 3 days when enough alternatives
exist. **`random`:** uniform sample. Deterministic tests seed via dependency-injected
`random.Random`.

### Misc

- `GET /api/health` → `{"status": "ok"}` (no auth).

---

## 6. Music provider strategy (MusicBrainz + Deezer + iTunes + Discogs + Cover Art Archive)

All provider code lives in `backend/src/providers/` behind one public interface so
routers never talk HTTP directly:

```python
# providers/__init__.py — the contract other code imports
def search_albums(query: str, limit: int = 20) -> list[SearchResult]: ...
def search_albums_detailed(query: str, limit: int = 20) -> SearchOutcome: ...  # results + degraded provider names for §5's X-Search-Degraded header (added by issue #2; additive)
def import_album(source: str, external_id: str) -> ImportedAlbum: ...  # raises ProviderError/NotFound
```

`SearchResult` and `ImportedAlbum` are plain dataclasses defined in `base.py`
(artwork URL, title/artist/year/label, and for import: full metadata + tracks with
durations in seconds + cover URL). Since issue #13, `ImportedAlbum` also carries
additive **source-breakdown fields** — `metadata_source`, `tracklist_source`,
`artwork_source` (each a provider name or `None`) and a per-source
`tracklists_by_source: dict[str, list[TrackInput]]` — so the import preview can
say which provider fed each part. They are filled in by `_assemble()` and import
behavior is unchanged (it still reads only `.tracks`).

### MusicBrainz

- Search: `GET https://musicbrainz.org/ws/2/release-group?query={q}&limit=N&fmt=json`
  → release groups (`id`, `title`, `artist-credit`, `first-release-date`).
- Import: `GET https://musicbrainz.org/ws/2/release/{mbid}?inc=recordings+artist-credits+labels+release-groups&fmt=json`
  → track `length` (ms → seconds), label, country, year.
- **Policy:** custom User-Agent `vynl/0.1.0 ({MUSICBRAINZ_CONTACT})`, **max 1
  request/second** — a module-level lock + spacing guard enforces this; search hits
  all providers concurrently but the MB leg waits its turn.

### Deezer

- Search: `GET https://api.deezer.com/search/album?q={q}&limit=N` (no key).
- Import: `GET https://api.deezer.com/album/{id}` → `tracks.data[]` with
  `duration` (seconds already), `cover_xl` artwork, label, release date.
- Deezer responses are fast and rich; used as the preferred tracklist source when a
  merged result has both ids.

### iTunes (issue #12)

- Search: `GET https://itunes.apple.com/search?term={q}&entity=album&limit=N&country={CC}`
  → `results[]` (`collectionId`, `collectionName`, `artistName`, `releaseDate`,
  `trackCount`, `artworkUrl100`, `country`). **No key, always on.**
- Import: `GET https://itunes.apple.com/lookup?id={collectionId}&entity=song&country={CC}`
  → the collection row + one row per song (`trackNumber`, `discNumber`,
  `trackTimeMillis`, `primaryGenreName`).
- **Multi-country:** search/lookup iterate `ITUNES_COUNTRIES` (default `US,JP,GB`);
  the first storefront that has the id supplies the album. Per-storefront failures
  **degrade** (try the next); only "every storefront failed" raises.
- **Rate limits:** no documented cap; vynl spaces storefront requests by a
  module-level **0.3 s floor** and uses a **20 s timeout**.
- Artwork upgrade: `…/100x100bb.jpg` → `…/600x600bb.jpg`. Tracklist sorted by
  `(discNumber, trackNumber)` for multi-disc releases.

### Discogs (issue #12)

- **Token-gated:** disabled when `DISCOGS_TOKEN` is blank — direct calls raise
  `ProviderError("Discogs is not configured")` and merged search omits it, so the
  app is fully functional without a token.
- Search: `GET https://api.discogs.com/database/search?q={q}&type=release&per_page=N&token=…`
  → `results[]`, `per_page` clamped to ≤ 100. Titles are usually
  `"Artist – Title"` (en-dash); split on the first spaced dash.
- Import: `GET https://api.discogs.com/releases/{id}?token=…` → `tracklist[]`
  (`duration` `"MM:SS"`/`"H:MM:SS"` → seconds, null-safe), `labels`, `genres`,
  `styles`, `formats`, `images` (prefer a ≥ 300 px full image; `spacer.gif`/
  `duck.gif` placeholder art counts as none).
- **Rate limits:** authenticated ~60 req/min → a module-level **1 req/s floor**
  plus retry with exponential backoff on HTTP 429 or
  `X-Discogs-Ratelimit-Remaining: 0`. Requests send
  `User-Agent: vynl/0.1.0 (+https://github.com/tylern4/vynl)`.

### Cover Art Archive (artwork)

- URL patterns: `https://coverartarchive.org/release-group/{mbid}/front-500` (and
  `/release/{mbid}/front` fallback); follows a 302 to archive.org; **404 = no art**.
- On import, artwork is **downloaded once** into `COVERS_DIR` (compose volume
  `covers_data` → `/app/covers`) as `{album_id}.{ext}` and served by
  `GET /api/albums/{id}/cover`. Deezer imports use `cover_xl` instead. If both fail,
  `cover_path` stays null and the frontend hotlinks `cover_url`.

### Merge / dedupe rules (search)

1. Query every enabled provider concurrently; failures degrade gracefully (§5).
2. Normalize: trim, lowercase, strip featuring suffixes (`"Artist feat. X"` →
   `"Artist"`) for **comparison only**.
3. Pair Deezer + MusicBrainz results where `artist`+`title` match (case-insensitive)
   and years are within ±1 (or one side has no year). Merged row:
   `source="musicbrainz"`, `external_id=` the MB release-group id, but carries
   `deezer_id` too so import can pull the Deezer tracklist.
4. Matching iTunes rows are then **absorbed** into an existing pair (adding
   `itunes_id`, filling year/track_count/cover only when still unknown), then
   matching Discogs rows likewise; a row that matches nothing is appended in
   provider order. This keeps the Deezer-first / MusicBrainz-canonical ordering
   byte-identical whether or not iTunes/Discogs contribute.

### Import rules

1. Metadata is canonical from MusicBrainz when its twin is known, else the
   requested source's own album, else the first provider that answered. Tracklist
   and artwork preference: **Deezer → iTunes → Discogs → MusicBrainz** (Cover Art
   Archive artwork is consulted last).
2. Artwork: Deezer `cover_xl` → iTunes 600 px → Discogs ≥ 300 px full image → CAA
   → none.
3. Duplicate check: `(source, external_id)` unique constraint **and** soft-dedupe
   on `(lower(title), lower(artist))` — both are global to the shared shelf (issue
   #14), so a second user importing the same release resolves to the existing
   album → 409 with its id in the detail.
4. The wire body carries a single `external_id` (§5), so "both ids known" means
   `import_album` resolved the counterpart id itself: it searches the *other*
   providers by normalized artist + title (year ± 1) and adopts a confident
   match ("twin discovery"). Discovery failure or a 404 on the counterpart
   degrades to a single-source import — never an error (issue #2
   clarification). iTunes and Discogs twins are discovered the same way; a
   Discogs import also records its `styles`/`formats` in the album's `metadata`
   JSONB, alongside the additive `itunes_id`/`discogs_id` (no new DB columns).

---

## 7. Frontend structure

Routes (react-router, `ProtectedRoute` wrapper same as reference):

| Route | Page | Contents |
| --- | --- | --- |
| `/login`, `/register` | auth pages | invite-code registration, identical flow to reference |
| `/` | `ShelfPage` | responsive cover grid ("the shelf"); instant filter box; tag chips sidebar/dropdown; sort selector; favorite toggle |
| `/album/:id` | `AlbumDetailPage` | large cover, metadata, **tracklist table** (position, title, length m:ss), tag editor (add/remove chips), "I spun this" play button + play history, edit note/favorite, remove from shelf |
| `/add` | `AddAlbumPage` | search box → merged results from `/api/search/albums` → one-click import with progress state; shows which source; already-added state; **clicking a result title opens the import-preview modal** (`POST /api/albums/preview`) showing the cover, full tracklist (with a per-source tracklist toggle when more than one provider offers one), and which provider fed each part before you commit (issue #13); a "Can't find it? Enter the album manually" secondary path links to `/add/manual` |
| `/add/manual` | `ManualAlbumPage` | manual entry form (title*/artist*/year/label/country/note) with a **dynamic tracklist editor** (per-row title + duration, entered as `m:ss` or plain seconds, add/remove rows); submit → `POST /albums/manual` → upload the picked cover → navigate to `/album/{id}`; a failed cover upload keeps the created album and offers inline retry (issue #11) |
| `/find` | `FindPage` | library-wide song/album/tag search across `/api/tracks` + `/api/albums`; results show song → its album; click through to detail |
| `/recommend` | `RecommendPage` | mode toggle (`dusty` / `random`), optional tag filter, big "Spin" button → recommendation card with reason + "Spun it" action |
| `/admin` | `AdminPage` | **admin-only** (`AdminRoute`; non-admins → `/`, anonymous → `/login`): add a user (name/email/password/role), list users with role select + status pills, approve/deny, inline reset-password, delete-with-confirmation; the current admin's own row is protected (issue #9) |

Conventions (match reference `api.ts` exactly): `request<T>` wrapper with
`/api` prefix, Bearer token in localStorage (`vynl_token`), `ApiError` class, 401 →
redirect to `/login`. `types.ts` mirrors the §5 JSON shapes. Styling:
`styles.css` with CSS variables, light/dark via `theme.tsx` toggle (persisted,
system default first visit), lucide-react icons, **no CSS framework**. Album cards
show `GET /api/albums/{id}/cover` with `cover_url` fallback and `loading="lazy"`.

**Cover art picker (issue #11):** `CoverPicker` is a reusable chooser with "Upload
image" (`<input type="file" accept="image/*">`) and "Take photo"
(`accept="image/*" capture="environment"` to open the phone camera). Before upload
the file is **normalized to a ≤ ~2000 px JPEG** via `createImageBitmap`/`<img>` +
canvas + `.toBlob('image/jpeg', 0.9)` (handles iOS HEIC and huge originals), previewed
as a blob URL, and removable. It's mounted on the `ManualAlbumPage` (upload after
creation) and on `AlbumDetailPage` ("Replace cover" — works for manual *and* imported
albums, uploads to the same `PUT /api/albums/{id}/cover` endpoint and updates in
place). Manual albums render a `source="manual"` `SourceBadge`.

Theming is two independent axes (`theme.tsx`): `data-theme="light|dark"` (persisted
under `vynl_theme`, system preference on first visit) plus a `data-palette` axis
persisted under `vynl_palette` (default `default`) selecting one of **eight curated
palettes** — default, citypop, cyberpunk, recordshop, hippie, deathmetal, punk,
classical — each shipped as a full light *and* dark token block in `styles.css`
(`:root[data-palette='<name>']` and `:root[data-palette='<name>'][data-theme='dark']`),
with the default palette reproducing the original warm tokens exactly. Palette and
mode are picked on the `/settings` page (gear icon in the top bar), which also
carries an admin-only **Manage users** entry linking to `/admin`; both saved
attributes are applied pre-first-paint by `index.html`'s inline guard so reloads
never flash the wrong colors.

Testing: Vitest + React Testing Library, same setup as reference
(`src/test/setup.ts`); every page/component gets a `.test.tsx` colocated.

---

## 8. Deployment (docker compose)

Baseline compose is committed with the plan; three services + two volumes:

- `db` — `postgres:16-alpine`, healthcheck `pg_isready`, volume `db_data`.
- `backend` — build `./backend`, env: `DATABASE_URL`, `JWT_SECRET`,
  `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `INVITE_CODE`,
  `MUSICBRAINZ_CONTACT`, `COVERS_DIR=/app/covers`; volume `covers_data` mounted
  there; `depends_on: db: service_healthy`; port 8000.
- `frontend` — build `./frontend`, nginx proxies `/api/` → `backend:8000`, SPA
  fallback, immutable asset caching (reference `nginx.conf` verbatim); port 8080→80.

`restart: unless-stopped` on everything. Migrations run on backend startup
(`run_migrations()` in lifespan, Alembic `compare_type=True`). CI
(`.github/workflows/ci.yml`, added in issue #7) runs backend pytest against a
Postgres service container, frontend `npm test` + build, then pushes images to GHCR
on `main`.

---

## 9. Testing strategy

- **Backend:** pytest against a disposable `<db>_test` Postgres database
  (reference `conftest.py` pattern: drop/create per session, `get_db` override).
  Provider tests mock HTTP with `httpx.MockTransport` — **no live network in CI**.
  Coverage targets: auth flow, import dedupe/409, tag replace semantics, play logging
  + `last_played_at` recompute, track search, dusty/random recommendation invariants
  (never-played first, respects tag filter, no duplicates in one response).
- **Frontend:** Vitest + RTL for pages (mock `fetch`), api.ts unit tests.
- **Smoke:** issue #7 runs `docker compose up` and hits health, register, import
  (cassette or live-tolerant), and the shelf render.

---

## 10. Milestones & issue breakdown

| # | Issue | Component | Depends on | Wave |
| --- | --- | --- | --- | --- |
| 1 | Backend foundation: config, database, models, Alembic, auth, users, health | backend | — | 1 |
| 2 | Music providers: MusicBrainz + Deezer + Cover Art Archive, merge logic, mocked tests | backend | — (contract: §6) | 2 |
| 3 | Collection API: import, albums CRUD, tracks, tags, plays, library search, recommendations endpoint | backend | 1, 2 | 2 |
| 4 | Frontend foundation: scaffold, api client, auth pages, routing, theme, nginx | frontend | — | 1 |
| 5 | Shelf & detail UI: cover grid, album detail + tracklist, add-album flow, tags UI, find page | frontend | 3, 4 | 3 |
| 6 | Recommendations UI: dusty/random picker wired to `/api/recommendations` | frontend | 5 | 4 |
| 7 | Integration: compose hardening, CI, README, screenshots, compose smoke test | infra | 3, 5, 6 | 5 |
| 8 | Polish: responsive passes, empty/error states, dark-mode audit | both | 5 | 4/5 (optional) |

Waves run in parallel: **wave 1** = issues 1+4 (disjoint directories), **wave 2** =
issues 2+3 (disjoint files inside `backend/`; issue 3 codes against the §6 provider
interface and mocks it in tests), **wave 3** = issue 5, **wave 4** = issues 6+8,
**wave 5** = issue 7.

---

## 11. Coordination protocol (agents)

1. **Issue tracker:** `ISSUES.md` is the index; each issue lives in
   `docs/issues/NNN-slug.md` with status (`open` → `in progress` → `done`), acceptance
   criteria checklist, and a per-issue "Notes" section. An agent claims an issue by
   setting `Status: in progress` + `Assignee:` **before starting work**.
2. **Worklog:** append a dated entry to `WORKLOG.md` when finishing (re-read the file
   immediately before appending; if it changed under you, append after the last
   entry). One bullet list: what shipped, key decisions, anything the next agent
   needs.
3. **Git:** agents **do not run git commands** — the coordinator reviews and commits
   per issue. This avoids index lock races between parallel agents.
4. **Scope:** only touch files your issue owns (see §3 layout). Cross-cutting needs →
   note in your issue file, don't edit another issue's files.
5. **Contract first:** if reality forces an API/shape change, edit `docs/PLAN.md` in
   the same change set and flag it in the worklog so the other side picks it up.
6. **Definition of done:** acceptance boxes checked, tests pass locally
   (`pytest` / `npm test`), issue status `done`, worklog entry appended.
