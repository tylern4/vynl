# #13: Import preview — click a search result to see what will be imported

- **Status:** done
- **Assignee:** agent-preview-13
- **Labels:** backend, frontend, features
- **Depends on:** #3 (import), #5 (AddAlbumPage); runs **after #10** (shares
  `styles.css`/`App.tsx` surface) and **before #12** (shares the provider layer)
- **Wave:** follow-up feature

## Summary

Merged search results can be assembled from several providers (today MusicBrainz +
Deezer; #12 adds iTunes + Discogs). A user wants to **click a result's title** and
see exactly what import would create *before* committing: cover, metadata,
tracklist with durations, and which provider fed each part. The preview also lets
them compare each contributing source's tracklist and pick the right pressing,
and it detects cases like "this would import the Joe Satriani cover of a Steve
Wonder song" by eyeballing the actual tracks.

## Design

**Dry-run semantics — the preview IS the import, minus persistence.** Add
`POST /api/albums/preview` with the *same* request body as `POST /api/albums/import`
(`{source, external_id}`). It calls `providers.import_album(source, external_id)`
— the identical assembly code path (incl. twin discovery) — and returns what import
would persist. No album row is created; **no dedup/409 check** (unlike import —
preview must work when the album is already on the shelf; the modal handles 409
at import time). Errors map the same way as import: `NotFound` → 404
`"Album not found at the provider: …"`, other `ProviderError` → 502.

## Backend

### Provider layer (additive, no behavior change to import)
- `backend/src/providers/base.py` — `ImportedAlbum` gains three `str | None`
  fields (default `None`): `metadata_source`, `tracklist_source`,
  `artwork_source`, and `tracklists_by_source: dict[str, list[TrackInput]]`
  (default empty dict).
- `backend/src/providers/__init__.py` `_assemble(...)` sets them:
  - `metadata_source`: `"musicbrainz"` if MB present else `"deezer"` if Deezer
    present else `None`.
  - `tracklist_source`: `"deezer"` when Deezer tracks win (§6 preference),
    `"musicbrainz"` when MB tracks are the fallback, else `None`.
  - `artwork_source`: `"deezer"` if the Deezer cover URL was used,
    `"cover_art_archive"` if CAA resolved it, else `None`.
  - `tracklists_by_source`: each contributing source's full tracklist
    (`{"deezer": […], "musicbrainz": […]}`; only non-empty lists; the preferred
    one is always included). Import keeps reading only `.tracks`.

### Endpoint + schema
- `backend/src/schemas.py`:
  - `TrackPreviewOut { position: int, title: str, duration_seconds: int | None = None }`.
  - `AlbumPreviewOut { source, external_id, title, artist, year, label, country,
    cover_url, track_count, tracks: list[TrackPreviewOut],
    source_breakdown: {metadata_source, tracklist_source, artwork_source} (nullable
    strings), tracklists_by_source: dict[str, list[TrackPreviewOut]] }`.
- `backend/src/routers/albums.py`: `POST /albums/preview` (auth via
  `get_current_user` — it's read-only, not `require_write`), body
  `AlbumImportRequest` (reuse; update the `Literal` when #12 adds sources),
  maps errors as above, no DB writes, `response_model=AlbumPreviewOut`.

### Tests (`backend/tests/`)
- Preview returns the same title/artist/tracks as a real import of the same id
  (mock both providers); tracks ordered by position; breakdown fields correct
  for (a) MB-only, (b) Deezer-only, (c) merged (MB metadata + Deezer
  tracklist/cover); `tracklists_by_source` contains both when merged and only
  the one when single-source.
- 404 on unknown id, 502 on provider failure, 422 on invalid body, and **no row
  persisted** (assert album count unchanged / no HTTP side effect) — also that
  duplicate-on-shelf does NOT 409 for preview.
- 40x mapping parity with import for the same mocked upstreams.

## Frontend

- `frontend/src/types.ts`: `TrackPreview`, `AlbumSourceBreakdown`, `AlbumPreview`
  (+ `tracklists_by_source: Record<string, TrackPreview[]>`).
- `frontend/src/api.ts`: `previewAlbum(data: AlbumImport): Promise<AlbumPreview>`
  → `POST /albums/preview`.
- `frontend/src/components/AlbumPreviewModal.tsx` (new):
  - `role="dialog"`, `aria-modal`, labelled by the album title; close on Esc and
    backdrop click/close button; focus moved in on open and restored on close
    (#8 conventions).
  - Content: `CoverImage` (albumId `null` + preview `cover_url`), title/artist,
    metadata line (year · label · country · N tracks), the row's `SourceBadge`,
    tracklist rendered with detail-page conventions (`.tracklist-scroll`,
    durations via `format.ts`), and a **Sources** section:
    - breakdown badges ("Metadata from MusicBrainz", "Tracklist from Deezer",
      "Artwork from Deezer") — badge skips a part when `null`;
    - if more than one contributing source has a tracklist, a small
      **tracklist source toggle** (buttons per source, showing track counts,
      e.g. "Deezer · 16 tracks" / "MusicBrainz · 14 tracks") with the preferred
      one preselected — this is the "choose the better match" affordance
      (mismatched counts are the classic wrong-pressing tell).
  - Footer: Cancel + **Import this album** → existing `api.importAlbum` with the
    row's `source`/`external_id`; pending state; on success show a "On your shelf —
    view" link (navigates to `/album/{id}`); on 409 reuse `parseConflictId`
    (already exported/used by AddAlbumPage) and show the same inline state; other
    errors inline with retry.
  - Loading state inside the modal while preview fetches; preview error → inline
    error + retry (no modal dismissal).
- `frontend/src/pages/AddAlbumPage.tsx`: make the result **title clickable**
  (button-styled link, `aria-label` like "Preview “{title}” by {artist}") that
  opens the modal for that row. Keep the existing import button intact (fast
  path). Only one modal at a time; reuse the row's already-loaded data for the
  modal shell.
- Tests: `AlbumPreviewModal.test.tsx` (renders cover/tracklist/breakdown; toggle
  switches tracklists & persists selection in state; import success → view link;
  import 409 → "already in shelf"; Esc/backdrop close; fetch error + retry)
  and an AddAlbumPage test for "clicking the title opens the modal". Existing
  tests stay green; `npm test` + `npm run build`.

## Docs

- `docs/PLAN.md` §5: add the preview endpoint (dry-run, no side effects, 409 not
  raised). §6: note the assembled-album source breakdown fields. §7: preview
  modal on the Add page.
- README: one feature bullet.

## Acceptance criteria

### Backend

- [x] `backend/src/providers/base.py`: `ImportedAlbum` gains `metadata_source`,
      `tracklist_source`, `artwork_source` (`str | None`, default `None`) and
      `tracklists_by_source: dict[str, list[TrackInput]]` (default empty).
- [x] `_assemble()` fills the breakdown: `metadata_source` = `"musicbrainz"` if MB
      present else `"deezer"` if Deezer present else `None`; `tracklist_source` =
      `"deezer"` when Deezer tracks win (§6 preference) else `"musicbrainz"` when MB
      tracks fall back else `None`; `artwork_source` = `"deezer"` if the Deezer cover
      URL was used else `"cover_art_archive"` if CAA resolved it else `None`;
      `tracklists_by_source` = each contributing source's non-empty tracklist
      (preferred always included). **Import behavior unchanged — still reads only
      `.tracks`.**
- [x] `schemas.py`: `TrackPreviewOut`, `AlbumPreviewOut` with nullable-string
      `source_breakdown` and `tracklists_by_source: dict[str, list[TrackPreviewOut]]`;
      `routers/albums.py`: `POST /albums/preview` — auth via `get_current_user`
      (read-only, not `require_write`), body `AlbumImportRequest` (reused), maps
      errors like import (`NotFound` → 404 `"Album not found at the provider: …"`,
      other `ProviderError` → 502), **no DB writes, no 409**,
      `response_model=AlbumPreviewOut`.
- [x] Backend tests: preview returns the same title/artist/tracks as a real import
      of the same ids (both providers mocked); tracks ordered by position; breakdown
      fields correct for MB-only / Deezer-only / merged (MB metadata + Deezer
      tracklist/cover); `tracklists_by_source` contains both when merged and only
      the one when single-source; 404 on unknown id, 502 on provider failure, 422 on
      invalid body, **no row persisted**, duplicate-on-shelf preview returns 200
      (no 409); preview added to the read-only auth sweep. Full suite
      **182 passed** (was 172).

### Frontend

- [x] `types.ts`: `TrackPreview`, `AlbumSourceBreakdown`, `AlbumPreview` (with
      `tracklists_by_source: Record<string, TrackPreview[]>`); `api.ts`:
      `previewAlbum(data: AlbumImport): Promise<AlbumPreview>` → `POST /albums/preview`.
- [x] `AlbumPreviewModal.tsx`: `role="dialog"` + `aria-modal` + `aria-labelledby`
      (album title); Esc, backdrop click, and close button all dismiss; focus moved
      in on open and restored on close; body scroll locked while open (#8
      conventions). Content: `CoverImage` (albumId `null` + preview `cover_url`),
      title/artist, metadata line (year · label · country · N tracks), the row's
      `SourceBadge`, tracklist with detail-page conventions
      (`.tracklist-scroll`, durations via `format.ts`), and a **Sources** section:
      breakdown badges ("Metadata from MusicBrainz", "Tracklist from Deezer",
      "Artwork from Deezer"; skipping any `null` part); a **tracklist source toggle**
      (buttons per source with track counts, preferred preselected, persisted in
      state) when more than one contributing source has a tracklist. Footer: Cancel
      + **Import this album** via `api.importAlbum` — pending state, success →
      "On your shelf — view" link to `/album/{id}`, 409 → same inline already-in-
      shelf state as AddAlbumPage (via `parseConflictId`), other errors inline with
      retry. Inline preview loading state and preview error + retry (no dismissal).
- [x] `AddAlbumPage.tsx`: result **title is clickable** (button-styled link,
      `aria-label` like `Preview “{title}” by {artist}`) and opens the modal for that
      row; fast-path import button kept; one modal at a time; modal shell reuses the
      row's already-loaded data.
- [x] Frontend tests: `AlbumPreviewModal.test.tsx` (renders cover/tracklist/
      breakdown; toggle switches tracklists & persists in state; import success →
      view link; import 409 → already-in-shelf; Esc/backdrop close; fetch error +
      retry), an AddAlbumPage test for "clicking the title opens the modal", and an
      api test for `previewAlbum`. Existing tests stay green — `npm test`
      **117 passed** (was 108), `npm run build` green.

### Docs

- [x] PLAN.md §5: preview endpoint (dry-run, no side effects, 409 not raised) +
      `AlbumPreviewOut` contract; §6: source-breakdown fields paragraph; §7: preview
      modal on the Add page.
- [x] README: one feature bullet.
- [x] WORKLOG entry written; issue marked done.

## Notes

- Rate cost: preview triggers the same upstream calls import would (MB fetch +
  Deezer search/fetch + CAA) — at most a few requests, fine under the 1 req/s
  MB throttle.
- #12 later generalizes these providers (itunes/discogs): its spec must keep the
  preview endpoint + breakdown + `tracklists_by_source` working for new sources
  and extend the request `Literal`s. Coordinate the `_assemble` change so #13
  lands first.

### Agent notes (agent-preview-13, 2026-10-08)

- All criteria checked; backend pytest **182 passed**, frontend `npm test`
  **117 passed**, `npm run build` green. Full detail in WORKLOG.md entry
  `2026-10-08 — Issue #13 import preview`.
- No deviations from the spec. Conventions reused from AddAlbumPage: `parseConflictId`
  is simply **exported** from `AddAlbumPage.tsx` (ESM cycle verified via tests +
  build), and the modal's import 409 state shows the same "already on your shelf —
  View album" inline link wording.
- Notes for #12 (more providers): the preview endpoint, breakdown fields, and
  `tracklists_by_source` are source-agnostic and generalize as-is; the only touched
  surface is the `source` `Literal` in `AlbumImportRequest` (update when itunes/
  discogs land). The docker `vynl-frontend` container on :8081 still serves a stale
  pre-#8 build — `npm run dev` on 5173 was the source of truth for frontend checks.