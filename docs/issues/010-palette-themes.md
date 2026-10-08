# #10: Color palette themes + settings menu

- **Status:** open
- **Assignee:** unassigned
- **Labels:** frontend, features, ui
- **Depends on:** #8 (theme system just polished — build on it)
- **Wave:** follow-up feature

## Summary

Extend theming beyond the light/dark toggle to a **palette** system: a set of curated
color palettes, each fully defined for light and dark modes, selectable from a
**settings menu**. Palettes start with: **default** (current warm look, unchanged),
**city pop**, **cyberpunk**, **record shop**, **70s hippie**, **death metal**, **punk**,
and **classical**.

## Design constraints (binding)

- **Backward compatible with #8's work.** The default palette must reproduce the
  current light/dark tokens *exactly* (zero visible regression; contrast ratios from
  #8 are the bar). The theme toggle keeps working; the palette is a second,
  independent axis stored separately.
- New axis = `data-palette` attribute on `<html>`, values `default | citypop |
  cyberpunk | recordshop | hippie | deathmetal | punk | classical`. Existing
  `data-theme="light|dark"` stays. Combined selector shape, e.g.
  `:root[data-palette='cyberpunk']` and `:root[data-palette='cyberpunk'][data-theme='dark']`.
- Persistence: `localStorage` key `vynl_palette` (default `default`; system-scheme
  fallback for the mode axis already exists). `index.html`'s inline FOUC-guard
  script must ALSO set the saved palette before first paint.
- Token vocabulary in `styles.css` stays the same (--bg, --surface, --surface-alt,
  --border, --text, --muted, --accent, --accent-dark, --accent-ink, --on-accent,
  --hover, --danger, --danger-bg, --danger-border, --mb, --mb-border, --backdrop,
  --shadow; radii/spacing untouched). Each palette = both mode blocks. A palette may
  choose to vary `color-scheme` per mode as today.
- **Contrast floor (WCAG AA on text):** body text on --bg/--surface ≥ 4.5:1, muted ≥
  3:1 where used as text, and `--on-accent` must pass ≥ 4.5:1 against `--accent`
  (choose dark-on-light accents where a neon would otherwise fail — e.g. near-black
  text on neon magenta). Prefer darker/desaturated accent variants for buttons and
  reserve the wildest colors for `--accent-ink` accents/borders. Record final ratios
  in the issue Notes.

## Palette reference (research-backed starting hexes — refine for contrast, cite what you change)

- **City pop** — pastel sunset + synthwave pastels: periwinkle `#4C5DD7`, deep violet
  `#260B68`, magenta `#C231C9`, light blue `#68A2EB`, sunset `#FCD84A #F97F41
  #F15050`, pink `#D23B7B`. Dark = deep indigo-violet surfaces (`#1D0225`/`#260B68`
  family), light = soft rose-paper with periwinkle buttons.
- **Cyberpunk** — near-black navy base `#0B0D17`, neon magenta `#FF2DAA`, neon cyan
  `#00E5FF`, electric violet `#7C4DFF`, off-white text `#C9D1D9`. Dark-first; light
  mode = pale cool surfaces with deep magenta `#C01A86` buttons and navy text
  `#0B0D17`, muted cyan accents.
- **Record shop** — aged cream paper, espresso/wood browns, burnt orange `#D16216`,
  amber `#F2992D`, olive `#494A24`, deep maroon `#511F27`, raspberry `#AB4265`.
  Light = cream + burnt-orange buttons; dark = walnut-brown surfaces + amber links.
- **70s hippie** — sunflower `#E6D021`, amber `#E29E28`, terracotta `#D7573B`, muted
  teal `#73A5A8`, slate indigo `#646199`. Light = cream + terracotta buttons; dark =
  deep umber + terracotta/teal accents.
- **Death metal** — pure black `#000`/`#0D0C0B`, blood red `#780606`-`#A3121F`,
  grays, bone/off-white text, optional sickly green accent. Dark = black + blood-red
  buttons (bone text on red for contrast); light = bone/flesh-gray paper + deep
  blood-red buttons.
- **Punk** — high-contrast zine: black `#000`, white `#FFF`, album red `#C81D1D`,
  acid green `#74E85C`, zine yellow `#F0B54D`. Bold black borders, red buttons, acid
  accents; light = off-white paper + near-black borders.
- **Classical** — ivory `#F8F5EF`, cream `#F7F1E3`, deep navy `#14213D`/`#1A1E2E`,
  gold `#C9A227`-`#FCA311` (darken gold for button contrast). Light = ivory + gold-
  navy; dark = navy surfaces + bright gold accents (dark ink on gold buttons).

## Acceptance criteria

- [ ] `theme.tsx` reworked: `Palette`/`PaletteName` + `getInitialPalette`,
      `applyPalette` (sets `data-palette`), `useTheme()` returns `{mode, palette,
      setMode, setPalette}` (keep existing consumers working — adapt their imports).
- [ ] Palette catalog data (id, label, preview swatches/hex per token) exposed for
      the settings UI; swatch previews render from the actual token values.
- [ ] `styles.css`: all 8 palettes × both modes as token blocks; default = current
      tokens byte-identical; every component continues to use the same var names.
- [ ] `index.html` FOUC guard also applies saved palette pre-paint.
- [ ] **Settings page** at `/settings` (nav gear icon, accessible label): palette
      grid — one card per palette with color swatches + name + "current" state,
      click to apply (persisted immediately, no reload); light/dark toggle also
      available there; shortcut explanation that the top-bar toggle still flips
      mode. Mobile-friendly layout in keeping with #8.
- [ ] Top bar: gear/`Settings` icon links to `/settings`; existing theme toggle
      preserved.
- [ ] Contrast pass per palette (record final ratios in the issue Notes); common
      components (buttons, chips, badges, skeletons, empty states) visually checked
      in both modes for every palette, incl. the MB badge.
- [ ] Tests: theme palette persistence + apply + FOUC-relevant behavior;
      `SettingsPage.test.tsx` (current tab, click switches palette + persists, mode
      toggle works, nav/a11y labels); existing 95 tests stay green. `npm test` +
      `npm run build` green.
- [ ] Docs: PLAN.md §7 (theme conventions) and README features updated to mention
      palettes + settings.
- [ ] Worklog entry; issue marked done.

## Notes

- Contrast floor is the hard requirement; exact hexes may drift from the reference
  values above to hit WCAG AA — when you adjust, keep the *mood* recognizable.
- Reuse #8's `:focus-visible`, `aria-live`, token-only rule — palettes must not
  introduce hardcoded colors outside `styles.css`.
- The in-flight screenshot refresh task targets the current default theme; your
  default palette must visually match what's captured there.