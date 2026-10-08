# #11: Manual album entry + cover upload / camera capture

- **Status:** open
- **Assignee:** unassigned
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

## Notes

- No DB migration needed: `source` is `String(20)`, `external_id` `String(64)` —
  `manual` + uuid fit as-is.
- Backend tests: run with the default `vynl_test` DB (existing conftest) — if another
  agent races it, re-run at the end.
- The #10 palette agent lands in `frontend` first — coordinate: this issue runs after
  #10 is committed to avoid edit overlap on shared files (`App.tsx`, `api.ts`,
  `styles.css`).