# #11: Manual album entry + cover upload / camera capture

- **Status:** done
- **Assignee:** agent-manual-11
- **Labels:** backend, frontend, features
- **Depends on:** #3 (album endpooints/artwork service), #5 (album UI); runs after #10 lands
- **Wave:** follow-up feature

## Summary

Obscure pressings are often missing from MusicBrainz/Deezer, so a user should be able
to add an album **manually** (title/artist/year/label/country/note and an optional
manual tracklist) and attach a cover from a **file upload** or, on a phone, **the
camera**.

## Backend

**`POST /api/albums/manual`** (auth, 201 → `AlbumOut` with tracks):
```jsonc
{
  "title": "Midnight Crush",          // required, trimmed 1..500
  "artist": "Tokyo Heartbeat",        // required, trimmed 1..500
  "year": 1983, "label": "...", "country": "JP",   //  optional
  "favorite": false, "note": "...",                 //  optional
  "tracks": [                        // optional; positions auto-assigned 1..n
    {"title": "...", "duration_seconds": 214}
  ]
}
```
- Persist `source="manual"`, `external_id=<uuid4().hex>` (the unique
  `(user_id, source, external_id)` needs a value), `cover_url=null`,
  `cover_path=null`, `metadata={}`; `track_count` denormalized; `last_played_at=null`.
- **Soft-dedupe** exactly like import: `(user_id, lower(title), lower(artist))` already
  exists → **409** `detail={"message":"...", "album_id": N}`.
- Validation: 422 on empty title/artist, all-whitespace title/artist, tracks with
  missing/empty titles, negative `duration_seconds`; year sane (1000–now+1).

**Cover upload** — `PUT /api/albums/{id}/cover`, multipart field `file` (auth,
ownership-scoped; 200 → `AlbumOut`, 400 on bad payload):
- Reject non-image bytes via existing `services.artwork.sniff_image` (jpeg/png/gif/webp),
  reject > `MAX_COVER_BYTES` (15 MB). Return 400 with a friendly detail, never 500.
- Add `store_cover_bytes(data: bytes, album_id: int) -> str` to
  `backend/src/services/artwork.py` (sniff → write `{album_id}.{ext}` under
  `covers_dir`, **delete any previously stored cover file for that album first** —
  filename may differ in ext, e.g. old `12.jpg` vs new `12.png`).
- Set `album.cover_path` to the returned filename; leave `cover_url` as-is (frontend
  serves local first; imported albums keep their remote url as a fallback).
- `GET /api/albums/{id}/cover` needs no changes (serves `cover_path`).

## Frontend

- **`/add` page**: add a clear secondary path "Can't find it? Enter manually" → nav
  to a new **`/add/manual`** route (nav via the existing Add page; a top-bar link is
  fine too).
- **`ManualAlbumPage`** (`/add/manual`): form for title*/artist*/year/label/country/
  note; **dynamic tracklist editor** (add/remove rows: title + duration; duration
  entered as `m:ss` or `ss` and converted to seconds; row validation; reorderable
  optional — append/remove is enough); submit → `createManualAlbum`; on **201** with a
  selected cover, immediately upload it, then navigate to `/album/{id}` (upload
  failure shows inline error with retry but does NOT undo the created album — tell the
  user the album exists and covers can be added from the detail page).
- **`CoverPicker`** component (reusable): image preview + controls:
  - "Upload image" → `<input type="file" accept="image/*">`;
  - "Take photo" → `<input type="file" accept="image/*" capture="environment">`
    (opens the camera on phones);
  - **Normalize to JPEG before upload**: read as `createImageBitmap`/Image + canvas,
    max dimension ~2000px, `.toBlob('image/jpeg', 0.9)` — handles HEIC from iOS
    cameras and huge originals; preview the normalized blob. Let user remove/retake.
- **`api.ts`** additions (additive, nothing renamed): `createManualAlbum(input)`,
  `uploadAlbumCover(id: number, blob: Blob): Promise<Album>` (raw `fetch` PUT with
  `Content-Type: image/jpeg` + Bearer; surfaces ApiError 400 detail). `types.ts`:
  `ManualAlbumInput`, `ManualTrackInput`, and extend `AlbumSource` with `'manual'`.
- **`AlbumDetailPage`**: add "Replace cover" that mounts `CoverPicker` and uploads to
  the same endpoint (works for manual and imported albums); updates in place.
- **`SourceBadge`**: render a `Manual` badge for `source === 'manual'` (no card art,
  fallback icon/placeholder since `cover_url` is null until upload).
- Layout/style/a11y conventions from #8/#10 (tokens only, focus-visible, labels).

## Tests

- **Backend** (`backend/tests/test_albums.py` or new `test_manual.py`): manual create
  happy path (+ track positions/count), 409 duplicate, 422 validations (blank title/
  artist, blank/negative durations), tracklist with duration omitted; cover upload OK
  (bytes served back via `GET /cover` with right content-type), non-image 400,
  oversized 400, replace (old file gone), ownership (other user's album → 404/403).
- **Frontend**: `ManualAlbumPage.test.tsx` (validation, add/remove tracks, m:ss
  parsing, submit → create + upload + navigate), `api.test.ts` new methods, detail
  page replace-cover flow (fetch mock), camera/upload inputs present with correct
  `capture`/`accept` attributes. Full suites green (`pytest` backend; `npm test` +
  `npm run build` frontend).

## Docs

- `docs/PLAN.md`: §5 add the two endpoints + note frontend JPEG normalization (HEIC/
  huge photos); §7 add `/add/manual` + `CoverPicker`; §4 note `source='manual'` and
  `external_id` uuid.
- README: feature bullet under Features.

## Acceptance criteria

### Backend

- [x] `POST /api/albums/manual` (auth + `require_write`, 201 → `AlbumOut` with
      tracks): persists `source="manual"`, `external_id` = fresh `uuid4().hex`,
      `cover_url`/`cover_path` null, `metadata_={}`, `track_count` denormalized,
      `last_played_at` null; track positions auto-assigned 1..n; title/artist
      trimmed (1..500).
- [x] Soft-dedupe exactly like import — `(user_id, lower(trim(title)),
      lower(trim(artist)))` already present → **409** `"Album already in your shelf
      (id=N)"` (same detail convention as `_conflict`).
- [x] `schemas.py`: `ManualTrackInput {title (1..500, not blank), duration_seconds:
      int | None (ge=0)}` and `ManualAlbumInput {title*, artist*, year?, label?,
      country?, favorite?, note?, tracks?}`; 422 on blank/all-whitespace title or
      artist, blank track title, negative `duration_seconds`, and year outside
      1000…now+1.
- [x] `PUT /api/albums/{id}/cover` (auth + `require_write`, 200 → `AlbumOut`):
      **raw-bytes PUT** (deviation from the issue's multipart wording — the
      `Content-Type` header is ignored, bytes are sniffed, so `python-multipart` is
      never installed). Ownership-scoped via `get_owned_album` (foreign/missing →
      404). Empty body / > `MAX_COVER_BYTES` (15 MB) / non-image bytes → friendly
      400 (never 500). `services.artwork.store_cover_bytes(data, album_id)` sniffs,
      **deletes any previously stored `{album_id}.*` first** (ext may differ), writes
      `{album_id}.{ext}`, and returns the filename (`None` → router 400). Sets
      `album.cover_path`, leaves `cover_url` as-is; `GET /cover` unchanged.
- [x] Backend tests (`backend/tests/test_albums.py`): manual happy path (201 + track
      positions/count), minimal album (no tracks), trimming, 409 soft-dupe, per-user
      isolation, read-only 403, 422 matrix (blank title/artist, blank track title,
      negative duration, year out of range + max-year okay); cover upload OK for
      jpeg+png with a bogus `Content-Type` (ignored), replace (old file deleted),
      non-image / oversized / empty → 400, replace on an imported album, foreign +
      missing album → 404, read-only 403; `store_cover_bytes` unit tests. Full suite
      **209 passed** (was 182).

### Frontend

- [x] `types.ts`: `ManualAlbumInput`, `ManualTrackInput`, and `AlbumSource` extended
      with `'manual'`; `api.ts`: `createManualAlbum(input)` → `POST /albums/manual`,
      `uploadAlbumCover(id, blob)` → raw `fetch` PUT with `Content-Type: image/jpeg`
      + Bearer that surfaces the API 400 detail.
- [x] `CoverPicker` component (reusable): "Upload image" (`<input type="file"
      accept="image/*">`) and "Take photo" (`accept="image/*" capture="environment"`
      — opens the camera on phones); normalizes to a JPEG (≤ ~2000 px longest side,
      quality 0.9) via `createImageBitmap`/`<img>` + canvas + `.toBlob('image/jpeg')`
      — HEIC-safe; previews the normalized blob and allows remove/retake.
- [x] `ManualAlbumPage` at `/add/manual`: form for title*/artist*/year/label/country/
      note with inline validation; **dynamic tracklist editor** (add/remove rows,
      duration entered as `m:ss` or plain seconds and converted, per-row validation);
      submit → `createManualAlbum` → on success uploads the picked cover → navigates
      to `/album/{id}`; a failed cover upload **keeps the created album** with an
      inline error + Retry upload + "view album" link; 409 soft-dupe shows the
      existing-album link; `/add` links "Can't find it? Enter the album manually".
- [x] `AlbumDetailPage` "Replace cover" mounts `CoverPicker` and uploads to the same
      endpoint (works for manual and imported albums), updates the album in place;
      `SourceBadge` renders a `Manual` badge for `source === 'manual'`.
- [x] Frontend tests: `ManualAlbumPage.test.tsx` (required-field + year + duration
      validation, add/remove tracks, m:ss/ss parsing, submit → create + upload +
      navigate, upload-failure retry, 409 link), `CoverPicker.test.tsx` (correct
      `capture`/`accept` attributes, normalization invoked + blob reported, remove
      clears, unreadable image error), `api.test.ts` (`createManualAlbum` JSON POST,
      raw-PUT `uploadAlbumCover` w/ bearer + 400 detail + network error),
      `AlbumDetailPage.test.tsx` (replace-cover success + failed-upload flow),
      `SourceBadge.test.tsx` (deezer/musicbrainz/manual), AddAlbumPage manual-link
      test. Existing tests stay green — `npm test` **142 passed** (was 117), `npm run
      build` green.

### Docs

- [x] PLAN.md §5: both new endpoints + `ManualAlbumInput` shape + raw-bytes PUT
      deviation note; §4: `albums.source` includes `manual` with a uuid `external_id`;
      §7: `/add/manual`, `CoverPicker` (JPEG normalization), replace-cover, manual
      badge.
- [x] README: one feature bullet under Features.
- [x] WORKLOG entry written; issue marked done.

## Notes

- No DB migration needed: `source` is `String(20)`, `external_id` `String(64)` —
  `manual` + uuid fit as-is.
- Backend tests: run with the default `vynl_test` DB (existing conftest) — if another
  agent races it, re-run at the end.
- The #10 palette agent lands in `frontend` first — coordinate: this issue runs after
  #10 is committed to avoid edit overlap on shared files (`App.tsx`, `api.ts`,
  `styles.css`).

### Agent notes (agent-manual-11, 2026-10-08)

- All criteria checked; backend pytest **209 passed** (was 182), frontend `npm test`
  **142 passed** (was 117), `npm run build` green. Full detail in WORKLOG.md entry
  `2026-10-08 — Issue #11 manual album entry`.
- **Deviation — raw-bytes PUT for the cover upload.** The issue said multipart
  (`field file`) and a `store_cover_bytes(data, album_id) -> str` returning the
  filename, but `python-multipart` is **not** in the backend requirements and
  adding it was out of scope. I implemented `PUT /api/albums/{id}/cover` as a
  raw-bytes body read via an async dependency (`read_raw_body(request)`), taking
  the endpoint otherwise sync like the rest of the router. `Content-Type` is
  ignored — bytes are sniffed — and `store_cover_bytes` returns `str | None`
  (None → router maps to 400) to preserve the artwork module's never-raise-into-a
  500 ethos.
- **409 detail shape.** The issue wrote `detail={"message": ..., "album_id": N}`;
  the existing import `_conflict` already used the string form
  `"Album already in your shelf (id=N)"` and the frontend's `parseConflictId`
  (AddAlbumPage) parses exactly that, so the manual endpoint reuses `_conflict`
  for full consistency. PLAN.md reflects the string form.
- The manual album's `external_id` is `uuid4().hex` (32 chars — fits the 64-char
  column); both `CoverImage` (via `getCoverBlob`) and the manual form assume covers
  are served from `GET /api/albums/{id}/cover`, which is unaffected.
- The docker `vynl-frontend` container on :8081 still serves a stale pre-#8 build —
  `npm run dev` on :5173 is the source of truth for the new `/add/manual` route.

### Coordinator follow-up (multipart conversion, 2026-10-08)

- Per user request, the cover upload was converted from the agent's raw-bytes PUT
  to the **multipart `file` field** the issue specified. Added
  `python-multipart==0.0.32` to `backend/requirements.txt` (+ venv install);
  the endpoint now takes `file: UploadFile = File()` with a bounded 64 kB-chunk
  read (`read_cover_bytes`, fails fast past `MAX_COVER_BYTES`), keeps sniff
  validation, and returns the same 400 family. Frontend `uploadAlbumCover` sends
  `FormData` (`file` = JPEG blob) without a manual Content-Type so the browser
  sets the boundary. Backend + frontend tests updated to multipart payloads.
  Byte-sniffing still governs, so camera captures from any client work
  identically.