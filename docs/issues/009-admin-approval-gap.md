# #9: Admin approval gap — pending accounts have no UI path to approval

- **Status:** done
- **Assignee:** coordinator
- **Labels:** backend, frontend, bug
- **Depends on:** none
- **Wave:** follow-up (after 7/8)

## Summary

Registration follows the reference app's invite-code model: the **first** account to
register becomes `admin` + `active`; every later signup is created `pending` and must
be approved by an admin. The backend exposes approval routes (`PATCH /api/users/{id}`
with `{status:"active"}` plus the action routes), but the **frontend has no admin
page** (scoped out of v1), so a non-first registration has no product path to
approval — it is a login dead-end unless someone edits the DB or curls the API.

This actually bit the owner during smoke testing: leftover smoke accounts registered
before the real account, so the owner's signup sat `pending` until fixed manually via
SQL (§ "Oct 8 incident" below).

## Acceptance criteria

- [x] Decide the policy — **chose (a): build a small admin page** wired to the
      existing `GET/PATCH /api/users` routes (plus a new admin-only
      `POST /api/users` for direct creation). Registration keeps the current
      invite + pending semantics; admins now have a product path to approve.
- [x] Route `/admin`, visible only to `role=admin` users (admin-only nav link +
      `AdminRoute` guard), listing users with status/role, approve/deny, inline
      reset-password, role switch, and delete with confirmation; follows the
      shelf UI conventions (`.card.section`, `.btn`, status pills).
- [x] Admin-only `POST /api/users` so an admin can add a user directly (active
      from the start, role selectable) — satisfies "add new users" without the
      invite/approval dance.
- [x] Covered the "second signup" scenario: admin approves a pending user and
      they can then log in (backend), plus frontend tests for the admin UI and
      access control (`AdminRoute`).
- [x] Updated PLAN.md §5 (auth contract + admin panel + create endpoint). No
      data-model change needed.
- [x] Worklog entry appended; issue marked done.

## Decision

Option **(a)**. The approval routes already existed and worked; the missing piece
was a UI. A small admin page is also the natural home for future user
administration, and avoids changing the registration/`pending` semantics that the
rest of the app (and tests) already rely on. The owner's account stays the only
admin until they add another.

## Notes

Reference: `backend/src/routers/{auth,users}.py` (approval routes exist), frontend has
no admin UI. PLAN §5 currently says "v1 keeps the reference's admin-approval flow" —
that sentence is part of what this issue revises.

## Oct 8 incident (context)

Live smoke-test accounts (`shelf5@…`, `rec-check@…`, `smoke-admin@…`,
`shelf-demo@…`) registered in the dev DB before the owner's real account. Owner's
account sat `role=user status=pending` and could not log in. Coordinator promoted the
owner's account to `admin+active` via SQL and wiped smoke accounts (the wipe raced an
in-flight agent which re-seeded `shelf-demo@…`; a post-wave cleanup pass removes all
non-owner data when issues #7/#8 finish).

**Lesson for the project:** dev-DB hygiene — agents doing live smoke checks should
use a scratch database (`vynl_smoke`) or the owner's DB only when the owner isn't
using it. See WORKLOG Oct 8 entry.
## Outcome (2026-10-09)

- **Backend:** `POST /api/users` (admin-only) creates an active user directly —
  `UserCreate { name, email, password, role=user, status=active }`; 409 on a
  duplicate email, 422 on short password / bad email; mirrors `/auth/register`.
  The existing approve/deny/role/reset-password/delete routes are unchanged.
  +8 tests in `test_auth.py` (now 37).
- **Frontend:** new `AdminPage` at `/admin` — add-user form, user table with
  role select, status pills, approve/deny, inline password reset, and
  delete-with-confirmation (the current admin's own row is protected: no
  deny/delete, role select disabled, "You" badge). New `AdminRoute` guard
  (non-admins → `/`; anonymous → `/login`) and an admin-only "Users" nav link.
  `api.ts` gains the user-management methods; `types.ts` gains `UserCreate`.
  +17 tests (13 AdminPage/AdminRoute, 4 api-client).
- **Docs:** PLAN §5 updated. No migration — no schema or columns changed.
