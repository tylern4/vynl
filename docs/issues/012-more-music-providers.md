# #12: More music providers — iTunes (multi-country) + Discogs

- **Status:** open
- **Assignee:** unassigned
- **Labels:** backend, features
- **Depends on:** #2 (provider architecture), #3 (search/import contract); runs after #10/#11 land
- **Wave:** follow-up feature

## Summary

MusicBrainz + Deezer under-cover obscure and international releases (esp. Japan).
Add **iTunes Search/Lookup** (no key; per-country storefront queries like `JP`) and
**Discogs** (vinyl-first; obscure pressings, formats, countries; needs a free personal
token, optional). Both plug into the existing `providers` interface, merge, and
import system; the frontend gains source badges and attribution only.

## Backend (bulk of the work)

### iTunes provider — `backend/src/providers/itunes.py` (no key, always on)
- Search: `GET https://itunes.apple.com/search?term={q}&entity=album&media=music&limit=25&country={cc}`
  for **each configured storefront** (see config). Map: collectionId, collectionName
  (title), artistName, year from releaseDate, trackCount, artworkUrl100 (upgrade to
  `600x600bb` — replace `100x100bb`), primaryGenreName (→ metadata), `country`.
- Import: `GET https://itunes.apple.com/lookup?id={collectionId}&entity=song&limit=200&country={cc}`
  → trackName + trackTimeMillis (ms → seconds); sort by `discNumber` then
  `trackNumber` (multi-disc albums); artwork via the same size upgrade.
- Polite behavior: small per-storefront spacing (≈0.3 s), 20 s timeout, per-storefront
  failure degrades (collect successes; only all-failed raises), empty result set for
  a storefront is not an error.
- `search_albums` returns iTunes rows sourced `"itunes"` with
  `external_id=str(collectionId)`, and **an `itunes_id` field** (additive) so merged
  rows can prefer iTunes tracklists/artwork too. ImportedAlbum gets `itunes_id`.

### Discogs provider — `backend/src/providers/discogs.py` (token-gated)
- **Disabled when `settings.discogs_token` is blank** (default). Search/import for
  source `discogs` while disabled → `ProviderError("Discogs is not configured")`; the
  merged search simply omits it.
- Search: `GET https://api.discogs.com/database/search?q={q}&type=release&per_page=20&token=…`
  → results: id, title (often `"Artist – Title"`, **parse** to artist+title), year,
  country, labels[], format[], `cover_image` (treat `spacer.gif`/duck.gif as no art),
  `thumb`.
- Import: `GET https://api.discogs.com/releases/{id}?token=…` → tracklist[] (title +
  `duration` `"MM:SS"`/`"H:MM:SS"` → seconds, null-safe), year, country,
  labels[].name, artists[].name, genres/styles (→ metadata), formats[] (→ metadata),
  images[] (pick first usable, prefer ≥300px; `uri150` as last resort; none → null).
- **Rate limits**: ~60 req/min authenticated — enforce a module-level token-bucket or
  1 req/s floor and back off on HTTP 429 / `X-Discogs-Ratelimit-Remaining: 0`; degrade
  (return partial) rather than raise unless the response is a hard 5xx. UA
  `vynl/0.1.0 (+https://github.com/tylern4/vynl)`.
- `SearchResult` gains additive `discogs_id`; `ImportedAlbum` gains `discogs_id`.

### Config / env
- `backend/src/config.py`: `discogs_token: str = ""`, `itunes_countries: str =
  "US,JP,GB"` (comma list, order = query order). `.env.example` documents both
  (`DISCOGS_TOKEN` blank by default; iTunes countries override for e.g. `US,JP,GB,DE,FR`).

### Merge + import (`providers/__init__.py`, `_merge.py`)
- Add iTunes + Discogs to the concurrent `search_albums` fan-out (collect
  per-provider failures as `degraded` like today; Discogs simply absent when
  disabled). Stable ordering: Deezer/MusicBrainz first, then iTunes, then Discogs.
- Dedupe/merge extends to the new sources (artist+title+year ±1 requires no change);
  merged rows fill `itunes_id`/`discogs_id` alongside existing ids. **Import rules
  (§6) only change additively**: an import may carry ids from several sources and
  the import fetch fans out over whichever are present; tracklist/artwork choice
  order stays Deezer → iTunes → Discogs → MusicBrainz lengths — document the new
  preference order in PLAN §6.
- No DB migration (only `metadata` JSONB carries extras; existing id columns
  `deezer_id`, `musicbrainz_release_group_id` unchanged — do NOT add DB columns).

## Frontend (small, cosmetic)

- `SourceBadge`: add `iTunes` and `Discogs` variants for `source === 'itunes' |
  'discogs'`. `types.ts`: extend `AlbumSource` union with `'itunes' | 'discogs'`
  (keep existing members; additive), extend `SearchResult` with optional ids if
  convenient (frontend doesn't need to act on them).
- `AddAlbumPage` attribution line updates to "MusicBrainz · Deezer · iTunes ·
  Discogs" and notes Discogs rows only appear when the token is configured.

## Tests

- Provider tests with mocked HTTP (no live calls): iTunes search/lookup mapping incl.
  ms→s, artwork size upgrade, multi-disc ordering, one-storefront-down degrade;
  Discogs disabled-when-no-token, `"A – T"` title parse, `MM:SS`→s incl. null, `spacer.gif`
  → None cover, 429 backoff/degrade, search+import.
- Merge integration: dedupe across 4 providers, single-provider down → degraded not
  error, import with multi-source ids assembling Deezer tracklist preference.
- No frontend visual tests required beyond existing patterns for SourceBadge if any;
  keep `npm test` green (no behavioral changes expected).

## Docs

- `docs/PLAN.md` §6: add the two providers (endpoints, rate limits, token gating,
  multi-country search, per-provider preference order for tracks/artwork). §5 stays
  unchanged (search/import contract identical; `X-Search-Degraded` header now may
  name `itunes`/`discogs`). README: features + config table mention iTunes countries
  and optional Discogs token.
- `.env.example` entries.

## Notes

- **Discogs token** is user-supplied (`/settings` remains out of scope): `.env.example`
  documents where to get one (account → Developers → Generate token). Feature must
  be fully functional without it (Discogs absent, everything else unaffected).
- Backend tests: run with the default `vynl_test` DB (conftest); if another agent
  races the DB, re-run at the end.
- Coordinate with #11’s manual-entry change if both edit frontend (SourceBadge is the
  only shared file — #11 adds a `manual` variant; prefer additive edits).