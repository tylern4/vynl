# #8: Polish — responsive passes, empty/error states, dark-mode audit

- **Status:** done
- **Assignee:** agent-polish-8
- **Labels:** frontend, ui, polish
- **Depends on:** #5 (pages exist); best run in wave 4–5 alongside #6/#7
- **Wave:** 4–5 (optional, lowest priority of the open issues)

## Summary

A dedicated sweep for quality: make every page hold up on phone + desktop, in both
themes, with nothing looking broken while loading or failing.

## Acceptance criteria

- [x] **Responsive audit** at 360 px, 768 px, 1280 px: shelf grid columns,
      album detail (cover stacks above tracklist), tracklist table (horizontal
      scroll or reflow, never squashed), add/search results, recommend cards,
      nav/top bar (collapse to a sane mobile pattern).
- [x] **Empty states** everywhere: empty shelf, no search results (external +
      library), no tags yet, no plays yet, empty recommendations (tag filter that
      matches nothing).
- [x] **Error states**: network failure / 5xx on every fetch-driven view shows a
      friendly message + retry, never a blank screen or infinite spinner; 401
      mid-session redirects cleanly; import failure shows what to try next.
- [x] **Loading states**: skeletons or spinners on shelf load, album detail,
      search-as-you-type (no flicker), recommendation spin.
- [x] **Dark mode audit**: all components use theme CSS variables (no hardcoded
      hex), contrast pass on text/borders/chips, cover images not washed out,
      toggle persists and initial paint respects system pref (no flash).
- [x] **Accessibility basics**: labels on inputs/buttons, focus-visible styles,
      alt text on covers, keyboard path through tag editor and import flow,
      `aria-live` on async result regions where cheap.
- [x] Visual consistency pass: spacing/radius/typography tokens used, lucide
      icons sized consistently, no stray default-blue links/buttons.
- [x] Tests for anything behavioral you changed; `npm test` + `npm run build`
      pass; screenshots (if #7 hasn't run yet, note that #7 captures them).

## Notes

- Work file-by-file; #6 may still be touching `RecommendPage.tsx` in wave 4 —
  check `ISSUES.md` status before editing shared components and coordinate via
  worklog.
- Do not refactor feature logic; this is presentation/robustness only.

### Agent notes (agent-polish-8, 2026-10-08)

- All criteria checked; `npm test` 95/95 + `npm run build` green. Full detail in
  WORKLOG.md entry `2026-10-08 — Issue #8 polish`.
- **Consciously deferred** (each verified, none blocking):
  - Rec-card layout extraction (#6 flagged it) — presentation-only issue; no new
    shared component to keep the diff small.
  - Keep `auto-spin-on-mount` on `/recommend`; no filter-change debounce added —
    `changeMode`/`pickTag` already invalidate in-flight requests via the request
    sequence ref and land on an explicit "idle" prompt, so there is no request
    storm to debounce.
  - No global fetch timeouts (shelves/recs can be slow with large libraries) —
    every promise has `finally`/`.catch` so a settle always clears its spinner;
    the only hang risk is a never-resolving network request, noted for later.
  - Shelf tag-filter shows only the "All" chip when there are no tags (intended);
    the "no tags yet" copy lives in the TagEditor ("No tags yet.") where tags are
    actually created.
  - `.fav-btn` white-on-scrim star stays white in both themes — it renders on top
    of artwork, not on a themed surface (kept `rgba` scrim + `--on-accent`).
- **Contract note for #7:** screenshots can use the new empty/error/skeleton
  states and the dark theme (now AA on muted text/buttons/MB badge).
