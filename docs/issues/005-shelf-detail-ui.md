# #5: Shelf & detail UI — cover grid, album detail, add-album flow, tags, find

- **Status:** done
- **Assignee:** agent-shelf-5
- **Labels:** frontend, ui
- **Depends on:** #3 (collection API), #4 (frontend foundation)
- **Wave:** 3

## Summary

Build the main user-facing views: the shelf (cover grid with filtering/sorting), the
album detail page (artwork + tracklist + tags + play logging), the add-album search/
import flow, and the find page for searching songs/moods across the library. Backend
endpoints are defined in [PLAN.md §5](../PLAN.md#5-api-contract).

## Acceptance criteria

**Shelf (`/` — `ShelfPage`)**

- [x] Responsive grid of album cards: cover from `GET /api/albums/{id}/cover` with
      `cover_url` fallback (broken-image fallback too), `loading="lazy"`, title +
      artist + year, favorite star, tag chips (first 2–3).
- [x] Client-side instant filter box (title/artist) hitting the already-loaded list;
      server params (`q`, `tag`, `favorite`, `sort`, paging) wired when filtering
      beyond the client set — pick one approach and note it in the worklog.
- [x] Tag filter (chips or dropdown from `GET /api/tags`), sort selector
      (added/title/artist/year/played), empty state ("Shelf is empty — add your
      first record") with CTA to `/add`.
- [x] Click card → `/album/:id`.

**Album detail (`/album/:id` — `AlbumDetailPage`)**

- [x] Large cover, title/artist/year/label/country, source badge, favorite toggle
      (`PATCH`), personal note editor.
- [x] **Tracklist table**: position, title, length formatted `m:ss` (null-safe
      "—"), total runtime footer.
- [x] **Tag editor**: current chips with × removal, input to add (existing tags
      from `GET /api/tags` autocomplete + free text), saves via
      `PUT /api/albums/{id}/tags` (replace semantics).
- [x] "I spun this" button → `POST /api/albums/{id}/plays`, shows
      `last_played_at` ("Last spun: 3 weeks ago"), play history list with
      delete.
- [x] Remove-from-shelf with confirmation → `DELETE` → back to `/`.
- [x] Loading, 404, and error states.

**Add album (`/add` — `AddAlbumPage`)**

- [x] Search box (debounced ~300 ms) → `GET /api/search/albums?q=` merged results:
      cover thumb, title, artist, year, track count, source badge (deezer/MB).
- [x] Import button per result → `POST /api/albums/import` with per-row pending
      state; on success navigate to `/album/{id}` (or show "On your shelf" +
      link); 409 → friendly already-added state linking the existing album;
      provider errors surfaced inline with retry.
- [x] Note in UI that search covers MusicBrainz + Deezer (attribution line).

**Find (`/find` — `FindPage`)**

- [x] One search box, two result sections: **songs** (`GET /api/tracks?q=` —
      title, artist, album, duration, cover thumb, click → album detail) and
      **albums** (`GET /api/albums?q=`), plus matching **tags** (from
      `GET /api/tags` filtered client-side) that jump to a filtered shelf
      (`/?tag=…`).
- [x] Works for "moods/vibes": typing a tag name surfaces the tag and its albums.
- [x] Empty + no-results states; debounced input; keyboard accessible.

**General**

- [x] All wiring uses `src/api.ts` (extend it if the stubs are missing methods);
      types from `src/types.ts` match PLAN §5.
- [x] Tests: `ShelfPage.test.tsx`, `AlbumDetailPage.test.tsx`,
      `AddAlbumPage.test.tsx`, `FindPage.test.tsx` (+ any new components) with
      mocked fetch: renders fixtures, filter/tag/sort interactions, import happy
      path + 409, tag add/remove, play logging, track search results. `npm test`
      and `npm run build` pass.

## Notes

- PLAN §5 shapes are final; if a gap blocks you, update PLAN.md and flag in worklog.
- Reuse #4's theme variables; no CSS framework; `lucide-react` icons.
- Issue #8 will do a dedicated responsive/error-state audit — basic states are
  still required here.
- **#5 implementation notes (agent-shelf-5):** single API addition;
  `src/api.ts` gained `getCoverBlob(id|Blob|null)` because the backend's
  `GET /api/albums/{id}/cover` is auth-gated (`get_current_user`) and a bare
  `<img>` cannot send the Bearer token — `CoverImage` fetches the cached cover
  through api.ts (blob URL) and falls back to `cover_url` → placeholder. All
  existing method names/types untouched. No PLAN.md edits were needed.
