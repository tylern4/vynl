# #2: Music providers — MusicBrainz, Deezer, Cover Art Archive

- **Status:** done
- **Assignee:** agent-providers-2
- **Labels:** backend, providers
- **Depends on:** none for structure; assumes #1's `requirements.txt` (httpx) exists
  — if #1 hasn't landed, add httpx yourself and note it in the worklog.
- **Wave:** 2 (runs in parallel with #3; owns only `backend/src/providers/` and
  `backend/tests/test_providers*.py`)

## Summary

Implement the music metadata provider layer described in
[PLAN.md §6](../PLAN.md#6-music-provider-strategy-musicbrainz--deezer--cover-art-archive):
a `providers/` package with a small public interface, clients for MusicBrainz
(search + release lookup), Deezer (search + album lookup), Cover Art Archive
(artwork URL resolution), merge/dedupe logic for combined search results, and an
`import_album` that assembles full album metadata + tracklist + artwork URL.

Issue #3 (collection API) codes against this interface and mocks it — the interface
must not change once committed.

## Public interface (contract — do not deviate without editing PLAN.md)

```python
# backend/src/providers/__init__.py
from .base import ImportedAlbum, ProviderError, SearchResult, TrackInput

def search_albums(query: str, limit: int = 20) -> list[SearchResult]: ...
def import_album(source: str, external_id: str) -> ImportedAlbum: ...
```

- `SearchResult`: dataclass — `source`, `external_id`, `title`, `artist`,
  `year: int | None`, `track_count: int | None`, `cover_url: str | None`,
  `label: str | None`, plus `deezer_id: int | None` and
  `musicbrainz_release_group_id: str | None` populated on merged rows.
- `ImportedAlbum`: dataclass — album fields (title, artist, year, label, country,
  source, external_id, both external ids, `cover_url`, `metadata: dict`) and
  `tracks: list[TrackInput]` where `TrackInput` = `position`, `title`,
  `duration_seconds: int | None`.
- `ProviderError(Exception)` with `.reason` for upstream failures;
  `NotFound(ProviderError)` for 404/unknown id (routers map these to 502/404).

## Acceptance criteria

- [x] `base.py` defines the dataclasses/protocol above; every provider returns
      them — routers never see provider-specific payload shapes.
- [x] **MusicBrainz**: release-group search
      (`/ws/2/release-group?query=…&fmt=json`) and release import
      (`/ws/2/release/{mbid}?inc=recordings+artist-credits+labels+release-groups&fmt=json`);
      `length` ms → `duration_seconds`; User-Agent
      `vynl/0.1.0 ({settings.musicbrainz_contact})`; **1 req/s enforced** by a
      module-level lock + minimum-interval guard.
- [x] **Deezer**: `/search/album` and `/album/{id}`; tracklist from
      `tracks.data[]` (`duration` already seconds), `cover_xl` as cover URL,
      label + `release_date` year.
- [x] **Search merge**: query both providers concurrently (threads or asyncio —
      httpx sync + `ThreadPoolExecutor` is fine), normalize for comparison
      (lowercase, trim, strip `feat.`/`ft.` suffixes), pair on
      artist+title with year ±1 or missing year, merged row prefers Deezer
      cover/track-count and MB year/label; unmatched pass through; stable order
      (Deezer relevance first, then MB). One provider failing → return the
      other's results (no exception escapes `search_albums` unless *both* fail).
- [x] **Import**: both-ids case fetches MB release (canonical metadata) and Deezer
      album (tracks + cover), falling back independently per source; artwork URL
      = Deezer `cover_xl` → Cover Art Archive
      (`coverartarchive.org/release-group/{mbid}/front-500`, then
      `/release/{mbid}/front`) → `None`. Artwork is **not downloaded** here —
      that's #3 (the URL is returned only).
- [x] Cover Art Archive 404 → `cover_url = None`, not an error; CAA/MB redirects
      followed.
- [x] Tests (`backend/tests/test_providers*.py`) use `httpx.MockTransport` (or
      monkeypatched `httpx.Client`) with recorded JSON fixtures — **zero live
      network calls**. Cover: single-source search, merged search, dedupe of
      identical albums, one provider down, MB length normalization, import
      fallback when Deezer 404s, NotFound propagation, CAA 404 → None.
- [x] `pytest` passes (provider suite: 27 passed; final full suite:
      163 passed, 0 failed).

## Notes

- PLAN §6 is the source of truth for URLs, merge rules, and rate limits.
- Keep provider HTTP in one `_client.py`-style helper so tests patch one seam.
- Env knobs come from #1's `settings` (`musicbrainz_contact`). If #1 isn't merged
  yet, import `settings` lazily or read env directly and note it.
- Do not touch routers, models, or schemas (#3 owns them).

### Contract additions (refinements to PLAN §6 — flagged in worklog)

- `search_albums_detailed(query, limit=20) -> SearchOutcome(results, degraded)`
  was added alongside the unchanged `search_albums`, so §5's
  `X-Search-Degraded` header can be set by #3's router. `search_albums` still
  returns `list[SearchResult]` exactly as committed.
- **Twin discovery** resolves the "both ids known" import rule: since the wire
  body carries only one id, `import_album` searches the *other* provider for
  the same album (normalized artist+title, year ±1) and fills the counterpart
  id, rather than requiring callers to pass both. Added as import rule 4 in
  PLAN §6.
- `search_albums_detailed` was added to the §6 contract block.

### Response-shape discoveries (verified live)

- MB release uses `label-info[].label.name`; positions come from
  `media[].track-offset + track[].position`; `release-group.first-release-date`
  is present when `inc=…release-groups`.
- MB unknown/invalid mbid → **400 "Invalid mbid."** (not 404); MB overloaded →
  503. `NotFound` is therefore only raised for search misses and Deezer-side
  unknown ids; MB 4xx on a release is treated as `NotFound`, 5xx/429 as
  `ProviderError`.
- Deezer unknown album id → **HTTP 200 + `{"error": {"code": 800}}`**; the
  client unwraps this into `NotFound`.
- Deezer `/search/album` rows omit `release_date`, so search-time `year` is
  `None` on Deezer rows (year arrives at import via `/album/{id}`).
- CAA answers HEAD 200 (redirect to archive.org) or 404 — used to probe
  artwork URLs without downloading bodies.
- MB-only search rows have `cover_url=None` (no unverified CAA URL at search
  time); merged rows are `source=musicbrainz` carrying `deezer_id`.
