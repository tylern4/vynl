# #3: Collection API — import, albums, tracks, tags, plays, search, recommendations

- **Status:** done
- **Assignee:** agent-collection-3
- **Labels:** backend, api
- **Depends on:** #1 (models/auth), #2 (provider interface — code against PLAN §6
  and mock it in tests if #2 is still in flight)
- **Wave:** 2 (parallel with #2; owns `backend/src/routers/{search,albums,tracks,
  tags,recommendations}.py`, album/track/tag schemas in `src/schemas.py`, artwork
  cache module, and their tests)

## Summary

Expose the full collection surface from [PLAN.md §5](../PLAN.md#5-api-contract):
external album search, import with artwork caching, album CRUD with tracklist,
tags, play logging, library song search, and the dusty/random recommendation
endpoint.

## Acceptance criteria

**Search & import**

- [x] `GET /api/search/albums?q=&limit=` → `SearchResult[]` as defined in PLAN §5
      (thin wrapper over `providers.search_albums`, provider shapes normalized to
      the documented JSON).
- [x] `POST /api/albums/import {source, external_id}` → 201 `AlbumOut`.
      - Calls `providers.import_album`, persists album + tracks, denormalizes
        `track_count`.
      - **Artwork caching:** download `cover_url` into `settings.covers_dir` as
        `{album_id}.{ext}` (httpx, size cap ~15 MB, sniff content-type), set
        `cover_path`; failure → leave `cover_path` null (never fail the import).
      - Duplicate: unique `(user_id, source, external_id)` **and** soft-dedupe on
        `(user_id, lower(title), lower(artist))` → **409** with existing album id
        in `detail`.
      - `NotFound` → 404, `ProviderError` → 502, with clear `detail`.

**Collection**

- [x] `GET /api/albums` — filters `q` (ILIKE title/artist), `tag` (exact, all-of
      if repeated), `favorite`, `sort` in `added|title|artist|year|played`
      (played = `last_played_at DESC NULLS LAST`), `limit`/`offset`; returns
      `AlbumOut[]` **with `tags[]` and without tracks**.
- [x] `GET /api/albums/{id}` — `AlbumOut` with `tracks[]` ordered by position;
      404 for other users' albums (ownership check on every endpoint).
- [x] `PATCH /api/albums/{id}` — `favorite? note? year? label?`.
- [x] `DELETE /api/albums/{id}` — 204 (cascade deletes tracks/tags links/plays).
- [x] `GET /api/albums/{id}/cover` — serve cached file with correct
      `Content-Type` + `Cache-Control: public, max-age=86400`; 404 if
      `cover_path` null or file missing; path traversal impossible (resolve
      within `covers_dir`).

**Tags**

- [x] `GET /api/tags` → `[{id, name, album_count}]`; `POST /api/tags {name}`
      idempotent (lowercase/trim, 422 empty, 409 not required — returning
      existing is enough); `PUT /api/albums/{id}/tags {tags: [...]}` **replaces**
      the set, creating missing tags; `DELETE /api/tags/{id}` 204.

**Plays**

- [x] `POST /api/albums/{id}/plays {played_at?}` → creates `Play`, updates
      `albums.last_played_at` to max(played_at); accepts backdated ISO datetime,
      rejects future dates (>5 min skew).
- [x] `GET /api/albums/{id}/plays` newest-first; `DELETE .../plays/{play_id}`
      204 and recomputes `last_played_at` (or null).

**Library search & recommendations**

- [x] `GET /api/tracks?q=&limit=` → `TrackSearchOut[]` (PLAN §5 shape: track
      fields + nested album summary), ILIKE across track title/album title/artist
      for the current user, ordered artist/title/position.
- [x] `GET /api/recommendations?mode=dusty|random&tag=&n=` → `RecommendationOut[]`
      with `album`, `reason`, `days_since_played`; dusty = bottom 25% by
      `COALESCE(last_played_at,'-infinity')` with random jitter, skip albums
      played within 3 days when alternatives exist, no duplicates in one
      response, `n` clamped 1–20; random = uniform sample. RNG injected
      (`random.Random`) so tests are deterministic.

**General**

- [x] Every endpoint requires an active user via #1's `get_current_user`; all
      ownership-scoped to `current_user.id`.
- [x] All request/response models added to `src/schemas.py` matching PLAN §5 JSON
      exactly (frontend will be built against them).
- [x] Tests: `test_search.py`, `test_albums.py`, `test_tags.py`, `test_plays.py`,
      `test_recommendations.py` — providers mocked at
      `providers.import_album`/`providers.search_albums` seam (no network).
      Cover: import happy path + 409 dup + 404 + 502, cover caching (incl.
      failure tolerance), filters/sort, tag replace semantics, play logging +
      last_played_at recompute, track search, dusty ordering invariants, random
      respects tag, auth 401s. `pytest` green.

## Notes

- PLAN §5 is the wire contract — do not rename fields; edit PLAN.md if you must.
- Import artwork download: store relative `cover_path` (filename only) so the
  volume mount stays portable.
- Keep routers thin; put import/cache/query logic in `src/services/` if it gets
  heavy (note the choice in the worklog).
- **`X-Search-Degraded` implemented** (originally flagged as unimplementable
  with the §6 signature; issue #2 later added `search_albums_detailed →
  SearchOutcome(results, degraded)` as an additive §6 line specifically for
  this). `GET /api/search/albums` now sets `X-Search-Degraded: <provider>`
  when one provider fails; body stays a plain `SearchResult[]`. Both failing
  still → 502. Header value is the provider *name* (e.g. `deezer`), per §5.
