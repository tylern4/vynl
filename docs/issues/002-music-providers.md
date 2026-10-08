# #2: Music providers — MusicBrainz, Deezer, Cover Art Archive

- **Status:** open
- **Assignee:** unassigned
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

- [ ] `base.py` defines the dataclasses/protocol above; every provider returns
      them — routers never see provider-specific payload shapes.
- [ ] **MusicBrainz**: release-group search
      (`/ws/2/release-group?query=…&fmt=json`) and release import
      (`/ws/2/release/{mbid}?inc=recordings+artist-credits+labels+release-groups&fmt=json`);
      `length` ms → `duration_seconds`; User-Agent
      `vynl/0.1.0 ({settings.musicbrainz_contact})`; **1 req/s enforced** by a
      module-level lock + minimum-interval guard.
- [ ] **Deezer**: `/search/album` and `/album/{id}`; tracklist from
      `tracks.data[]` (`duration` already seconds), `cover_xl` as cover URL,
      label + `release_date` year.
- [ ] **Search merge**: query both providers concurrently (threads or asyncio —
      httpx sync + `ThreadPoolExecutor` is fine), normalize for comparison
      (lowercase, trim, strip `feat.`/`ft.` suffixes), pair on
      artist+title with year ±1 or missing year, merged row prefers Deezer
      cover/track-count and MB year/label; unmatched pass through; stable order
      (Deezer relevance first, then MB). One provider failing → return the
      other's results (no exception escapes `search_albums` unless *both* fail).
- [ ] **Import**: both-ids case fetches MB release (canonical metadata) and Deezer
      album (tracks + cover), falling back independently per source; artwork URL
      = Deezer `cover_xl` → Cover Art Archive
      (`coverartarchive.org/release-group/{mbid}/front-500`, then
      `/release/{mbid}/front`) → `None`. Artwork is **not downloaded** here —
      that's #3 (the URL is returned only).
- [ ] Cover Art Archive 404 → `cover_url = None`, not an error; CAA/MB redirects
      followed.
- [ ] Tests (`backend/tests/test_providers*.py`) use `httpx.MockTransport` (or
      monkeypatched `httpx.Client`) with recorded JSON fixtures — **zero live
      network calls**. Cover: single-source search, merged search, dedupe of
      identical albums, one provider down, MB length normalization, import
      fallback when Deezer 404s, NotFound propagation, CAA 404 → None.
- [ ] `pytest` passes.

## Notes

- PLAN §6 is the source of truth for URLs, merge rules, and rate limits.
- Keep provider HTTP in one `_client.py`-style helper so tests patch one seam.
- Env knobs come from #1's `settings` (`musicbrainz_contact`). If #1 isn't merged
  yet, import `settings` lazily or read env directly and note it.
- Do not touch routers, models, or schemas (#3 owns them).
