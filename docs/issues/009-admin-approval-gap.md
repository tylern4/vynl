# #9: Admin approval gap — pending accounts have no UI path to approval

- **Status:** open
- **Assignee:** unassigned
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

- [ ] Decide the policy: (a) build a small admin page (list non-active users, Approve/
      Deny, role switch) wired to the existing `GET/PATCH /api/users` routes, **or**
      (b) change registration policy so a valid invite code grants active-from-start
      (simplest for a book-shelf app, e.g. keep the admin/user/read_only roles but
      skip `pending` unless an admin explicitly throttles registrations). Pick one,
      note the choice.
- [ ] If (a): route `/admin`, visible only to `role=admin` users, listing users with
      status/role, approve/deny/reset-password controls, consistent with shelf UI
      conventions; tests for both UI and access control.
- [ ] If (b): remove/repurpose `pending` semantics; adjust backend + frontend+ tests
      so any valid-invite registration is usable immediately; first-account admin
      rule still applies (or reconsider if the owner wants multi-admin).
- [ ] Either way: cover the "second signup" scenario with a backend test and a
      frontend test (register → can log in / or sees pending + how they get approved).
- [ ] Update PLAN.md §5 (auth contract) and the data-model section if semantics change.
- [ ] Worklog entry appended; issue marked done.

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