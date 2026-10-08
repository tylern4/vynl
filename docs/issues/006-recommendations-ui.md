# #6: Recommendations UI — dusty shelf picker

- **Status:** open
- **Assignee:** unassigned
- **Labels:** frontend, ui, features
- **Depends on:** #5 (shelf pages/patterns), #3 (endpoint must exist)
- **Wave:** 4

## Summary

The differentiating feature: a `/recommend` page that answers "what should I spin?"
— either the **dusty shelf** (records you haven't listened to in a while) or a
**random** pick, with tag/mood filtering.

## Acceptance criteria

- [ ] `/recommend` route + nav entry (icon e.g. `Dices`/`Disc3` from lucide),
      protected like other pages.
- [ ] Mode toggle: **Dusty** (default) vs **Random** with short explanations
      ("haven't spun in a while" / "pure chance").
- [ ] Optional tag/mood filter populated from `GET /api/tags` (multi-select chips
      allowed if easy; single select is acceptable).
- [ ] "Spin" button → `GET /api/recommendations?mode=…&tag=…&n=3` (n=3 feels
      right; adjust with a worklog note) → renders recommendation cards: cover,
      title, artist, **reason** ("Haven't spun this since Aug 2026" / "Never
      played" / "Random pick"), `days_since_played` badge.
- [ ] Per-card actions: **"Spun it"** → `POST /api/albums/{id}/plays` (then card
      shows logged state and Spin refreshes), **"Show me another"** (re-roll just
      that slot), click-through to `/album/:id`.
- [ ] Loading (spinner/skeleton), empty library state (link to `/add`), and error
      state (backend down / 502).
- [ ] Feels good: button focus states, disabled while spinning, no layout jump
      between spins.
- [ ] Tests: `RecommendPage.test.tsx` — mocked fetch fixtures for both modes,
      spin renders cards with reasons, "Spun it" posts + updates, empty library
      state, tag filter included in query. `npm test` + `npm run build` pass.

## Notes

- Endpoint contract: [PLAN.md §5](../PLAN.md#5-api-contract) (`RecommendationOut`).
- Backend dusty/random semantics live in issue #3 — build against the contract.
- Reuse #5's album card styling where sensible; extract a shared component if you
  find yourself duplicating (note extraction in worklog for #8).
