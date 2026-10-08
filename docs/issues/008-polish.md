# #8: Polish — responsive passes, empty/error states, dark-mode audit

- **Status:** open
- **Assignee:** unassigned
- **Labels:** frontend, ui, polish
- **Depends on:** #5 (pages exist); best run in wave 4–5 alongside #6/#7
- **Wave:** 4–5 (optional, lowest priority of the open issues)

## Summary

A dedicated sweep for quality: make every page hold up on phone + desktop, in both
themes, with nothing looking broken while loading or failing.

## Acceptance criteria

- [ ] **Responsive audit** at 360 px, 768 px, 1280 px: shelf grid columns,
      album detail (cover stacks above tracklist), tracklist table (horizontal
      scroll or reflow, never squashed), add/search results, recommend cards,
      nav/top bar (collapse to a sane mobile pattern).
- [ ] **Empty states** everywhere: empty shelf, no search results (external +
      library), no tags yet, no plays yet, empty recommendations (tag filter that
      matches nothing).
- [ ] **Error states**: network failure / 5xx on every fetch-driven view shows a
      friendly message + retry, never a blank screen or infinite spinner; 401
      mid-session redirects cleanly; import failure shows what to try next.
- [ ] **Loading states**: skeletons or spinners on shelf load, album detail,
      search-as-you-type (no flicker), recommendation spin.
- [ ] **Dark mode audit**: all components use theme CSS variables (no hardcoded
      hex), contrast pass on text/borders/chips, cover images not washed out,
      toggle persists and initial paint respects system pref (no flash).
- [ ] **Accessibility basics**: labels on inputs/buttons, focus-visible styles,
      alt text on covers, keyboard path through tag editor and import flow,
      `aria-live` on async result regions where cheap.
- [ ] Visual consistency pass: spacing/radius/typography tokens used, lucide
      icons sized consistently, no stray default-blue links/buttons.
- [ ] Tests for anything behavioral you changed; `npm test` + `npm run build`
      pass; screenshots (if #7 hasn't run yet, note that #7 captures them).

## Notes

- Work file-by-file; #6 may still be touching `RecommendPage.tsx` in wave 4 —
  check `ISSUES.md` status before editing shared components and coordinate via
  worklog.
- Do not refactor feature logic; this is presentation/robustness only.
