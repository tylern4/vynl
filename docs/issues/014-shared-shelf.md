# #14: Shared shelf + open registration

- **Status:** done
- **Assignee:** coordinator
- **Labels:** backend, auth
- **Depends on:** 9
- **Wave:** follow-up

## Summary

The collection is now a **single shared shelf** for every active user instead of
per-user shelves. Albums and tags are global: `albums.user_id` survives only as
attribution ("who added this record"), never as a scoping key, and tags have no
owner at all. Registration kept the invite code as a **bootstrap-only** gate: it
is required solely to create the very first account (which becomes `admin` +
`active`); later signups register freely and land `pending` until approved via
the #9 admin flow.

## Acceptance criteria

- [x] Albums dedupe globally: hard `(source, external_id)` unique constraint
      (`uq_albums_source_external`) and soft-dedupe on
      `(lower(title), lower(artist))`; `user_id` kept as attribution only.
- [x] Tags are global: `tags.user_id` dropped, single `uq_tags_name` per shelf;
      `album_tags` links repointed at the surviving tag during migration.
- [x] Every collection endpoint serves the shared shelf — list/detail/patch/
      delete/cover, play log/list/delete, tag replace/delete, track search,
      recommendations — with ownership-404s removed (write endpoints still via
      `require_write`).
- [x] Invite code required only for the first (bootstrap) account; later
      signups ignore it and land `pending`.
- [x] Migration `0002_shared_shelf.py` collapses pre-existing cross-user
      duplicate albums and duplicate tag names (earliest row wins) before adding
      the new constraints; `alembic check` reports no drift.
- [x] Backend suite updated for shared-shelf semantics — **251 passed**,
      frontend **164 passed** (no frontend behavior change; the Register page
      already labelled the field "Setup code (first account only)").

## Notes

- The 409 detail string is now `"Album is already on the shelf (id=N)"` (was
  "Album already in your shelf (id=N)"). Frontend AddAlbumPage parses the `(id=N)`
  part, so no client change was needed.
- No `PLAN.md` §4/§5/§6 ownership text is left over (see the diff in this issue).
- A pre-existing doc drift (coverage: PLAN still describes the raw-bytes PUT,
  the app moved to multipart) was left untouched — it belongs to #11, not this
  issue.