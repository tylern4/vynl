# vynl — Issue Tracker

Index of all implementation issues. One file per issue under
[`docs/issues/`](docs/issues/). This is the coordination surface for parallel work:
claim an issue by flipping it to `in progress` before starting, check off acceptance
criteria as you go, finish by marking it `done` and appending to
[WORKLOG.md](WORKLOG.md).

**Protocol:** see [docs/PLAN.md §11](docs/PLAN.md). Agents do not run git commands;
the coordinator commits.

| # | Title | Status | Depends on | Wave | Assignee |
| --- | --- | --- | --- | --- | --- |
| 1 | [Backend foundation](docs/issues/001-backend-foundation.md) | done | — | 1 | agent-backend-1 |
| 2 | [Music providers (MusicBrainz + Deezer + CAA)](docs/issues/002-music-providers.md) | done | — | 2 | agent-providers-2 |
| 3 | [Collection API (import, albums, tags, plays, search, recs)](docs/issues/003-collection-api.md) | done | 1, 2 | 2 | agent-collection-3 |
| 4 | [Frontend foundation (scaffold, auth, theme)](docs/issues/004-frontend-foundation.md) | done | — | 1 | agent-frontend-1 |
| 5 | [Shelf & detail UI](docs/issues/005-shelf-detail-ui.md) | done | 3, 4 | 3 | agent-shelf-5 |
| 6 | [Recommendations UI](docs/issues/006-recommendations-ui.md) | done | 5 | 4 | agent-recommend-6 |
| 7 | [Integration: compose, CI, README, smoke test](docs/issues/007-integration.md) | done | 3, 5, 6 | 5 | agent-integration-7 |
| 8 | [Polish: responsive, empty/error states, dark mode](docs/issues/008-polish.md) | done | 5 | 4–5 | agent-polish-8 |
| 9 | [Admin approval gap — pending accounts have no UI path](docs/issues/009-admin-approval-gap.md) | open | — | follow-up | — |
| 10 | [Color palette themes + settings menu](docs/issues/010-palette-themes.md) | done | 8 | feature | agent-palette-10 |
| 11 | [Manual album entry + cover upload / camera](docs/issues/011-manual-album-entry.md) | open | 3, 5 (after 10) | feature | — |
| 12 | [More music providers — iTunes (multi-country) + Discogs](docs/issues/012-more-music-providers.md) | open | 2, 3 (after 10, 11) | feature | — |
| 13 | [Import preview — click a search result to see what will be imported](docs/issues/013-import-preview.md) | open | 3, 5 (after 10, before 12) | feature | — |

Statuses: `open` → `in progress` → `done` (or `blocked` with a note).
