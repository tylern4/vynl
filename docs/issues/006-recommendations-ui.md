# #6: Recommendations UI — dusty shelf picker

- **Status:** done
- **Assignee:** agent-recommend-6
- **Labels:** frontend, ui, features
- **Depends on:** #5 (shelf pages/patterns), #3 (endpoint must exist)
- **Wave:** 4

## Summary

The differentiating feature: a `/recommend` page that answers "what should I spin?"
— either the **dusty shelf** (records you haven't listened to in a while) or a
**random** pick, with tag/mood filtering.

## Acceptance criteria

- [x] `/recommend` route + nav entry (icon e.g. `Dices`/`Disc3` from lucide),
      protected like other pages.
- [x] Mode toggle: **Dusty** (default) vs **Random** with short explanations
      ("haven't spun in a while" / "pure chance").
- [x] Optional tag/mood filter populated from `GET /api/tags` (multi-select chips
      allowed if easy; single select is acceptable).
- [x] "Spin" button → `GET /api/recommendations?mode=…&tag=…&n=3` (n=3 feels
      right; adjust with a worklog note) → renders recommendation cards: cover,
      title, artist, **reason** ("Haven't spun this since Aug 2026" / "Never
      played" / "Random pick"), `days_since_played` badge.
- [x] Per-card actions: **"Spun it"** → `POST /api/albums/{id}/plays` (then card
      shows logged state and Spin refreshes), **"Show me another"** (re-roll just
      that slot), click-through to `/album/:id`.
- [x] Loading (spinner/skeleton), empty library state (link to `/add`), and error
      state (backend down / 502).
- [x] Feels good: button focus states, disabled while spinning, no layout jump
      between spins.
- [x] Tests: `RecommendPage.test.tsx` — mocked fetch fixtures for both modes,
      spin renders cards with reasons, "Spun it" posts + updates, empty library
      state, tag filter included in query. `npm test` + `npm run build` pass.

## Notes

- Endpoint contract: [PLAN.md §5](../PLAN.md#5-api-contract) (`RecommendationOut`).
- Backend dusty/random semantics live in issue #3 — build against the contract.
- Reuse #5's album card styling where sensible; extract a shared component if you
  find yourself duplicating (note extraction in worklog for #8).

### Implementation notes (agent-recommend-6, 2026-10-08)

- **n=3** kept (slate of three cards; matches PLAN §5's example) via a
  `SPIN_COUNT` constant. Auto-spins once on page mount (StrictMode-safe ref
  guard) so loading/empty/error states are immediately visible; the "Spin"
  button re-rolls the whole slate with the current mode/tag.
- **Re-roll semantics:** "Show me another" refetches `n=1` with the same
  mode/tag and replaces just that slot; a request-sequence ref invalidates
  stale in-flight responses when the mode/tag/slate changes. Reroll avoids
  landing on a card already on screen (≤5 attempts, then accepts whatever) so
  tiny shelves don't loop forever.
- **"Spun it"** posts `logPlay(id)` and swaps the card's payload for the returned
  `AlbumOut` (`reason: "Logged — happy spinning!"`, `days_since_played: 0`),
  hiding the stale days badge until the card is re-rolled or Spin refires.
- Reused **`CoverImage`** (auth-gated cover blob → `cover_url` → placeholder) and
  `getTags()` chip styling (`.tag-chip`/`.tag-filter`) verbatim from #5; did not
  reuse `AlbumCard` — recommendation cards carry reason/badge/actions, so the
  layout differs; no shared component extracted (noted for #8). Added `Dices`
  to the top-bar Recommend link (other nav links stay text-only; #8 may want
  uniform nav icons) plus a small button `:focus-visible` polish block. No
  `api.ts`/`types.ts` changes needed — `getRecommendations`/`Recommendation`
  matched the live contract.
- Live-verified against a one-off backend container (port 18000; port 8000 was
  already bound by an unrelated process): register → flatted to admin+active in
  the dev DB → empty-library `[]`, populated dusty/random responses with
  `Never played` / `Haven't spun this since Oct 2026` / `Random pick` reasons
  and nullable `days_since_played`, `tag=chill` filtering, `tag=nope → []`,
  bogus mode → 422. Smoke user (`rec-check@example.com`, admin+active) +
  imported "Remain in Light" left in the dev `vynl` DB, mirroring #5's habit.
  Container removed.
- Tests: 11 in `RecommendPage.test.tsx`; suite total **92 passed**, build green.
