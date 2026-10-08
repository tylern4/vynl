# #10: Color palette themes + settings menu

- **Status:** done
- **Assignee:** agent-palette-10
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

- [x] `theme.tsx` reworked: `Palette`/`PaletteName` + `getInitialPalette`,
      `applyPalette` (sets `data-palette`), `useTheme()` returns `{mode, palette,
      setMode, setPalette}` (keep existing consumers working — adapt their imports).
- [x] Palette catalog data (id, label, preview swatches/hex per token) exposed for
      the settings UI; swatch previews render from the actual token values.
- [x] `styles.css`: all 8 palettes × both modes as token blocks; default = current
      tokens byte-identical; every component continues to use the same var names.
- [x] `index.html` FOUC guard also applies saved palette pre-paint.
- [x] **Settings page** at `/settings` (nav gear icon, accessible label): palette
      grid — one card per palette with color swatches + name + "current" state,
      click to apply (persisted immediately, no reload); light/dark toggle also
      available there; shortcut explanation that the top-bar toggle still flips
      mode. Mobile-friendly layout in keeping with #8.
- [x] Top bar: gear/`Settings` icon links to `/settings`; existing theme toggle
      preserved.
- [x] Contrast pass per palette (record final ratios in the issue Notes); common
      components (buttons, chips, badges, skeletons, empty states) visually checked
      in both modes for every palette, incl. the MB badge.
- [x] Tests: theme palette persistence + apply + FOUC-relevant behavior;
      `SettingsPage.test.tsx` (current tab, click switches palette + persists, mode
      toggle works, nav/a11y labels); existing 95 tests stay green. `npm test` +
      `npm run build` green.
- [x] Docs: PLAN.md §7 (theme conventions) and README features updated to mention
      palettes + settings.
- [x] Worklog entry; issue marked done.

## Notes

- Contrast floor is the hard requirement; exact hexes may drift from the reference
  values above to hit WCAG AA — when you adjust, keep the *mood* recognizable.
- Reuse #8's `:focus-visible`, `aria-live`, token-only rule — palettes must not
  introduce hardcoded colors outside `styles.css`.
- The in-flight screenshot refresh task targets the current default theme; your
  default palette must visually match what's captured there.

### Final contrast ratios (light / dark, WCAG AA pair-ratio)

Every binding floor passes for all 8 palettes in both modes: `--text` on
`--bg`/`--surface` ≥ 4.5, `--muted` ≥ 3 (all > 4.5 in practice), `--on-accent`
on `--accent` ≥ 4.5, `--mb` on `--surface` ≥ 4.5. Verified with a node
relative-luminance script against the exact `styles.css` tokens.

| palette | text/bg | text/surface | muted/surface | on-accent/accent | on-accent/accent-dark | mb/surface | danger/danger-bg | accent-ink/surface |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| default | 13.18 / 14.62 | 14.36 / 13.24 | 4.92 / 5.95 | 4.58 / 4.58 | 5.84 / 5.84 | 5.31 / 7.46 | 4.76 / 5.77 | 4.58 / 7.59 |
| citypop | 14.38 / 17.12 | 16.00 / 15.55 | 5.83 / 7.72 | 5.45 / 4.96 | 7.00 / 6.55 | 4.91 / 8.62 | 5.15 / 6.60 | 10.32 / 5.40 |
| cyberpunk | 16.50 / 12.55 | 19.37 / 11.53 | 6.68 / 5.79 | 5.63 / 5.63 | 7.59 / 7.59 | 5.54 / 10.01 | 4.59 / 6.01 | 5.59 / 11.57 |
| recordshop | 13.05 / 13.49 | 14.57 / 12.14 | 5.92 / 6.86 | 5.23 / 5.23 | 6.92 / 6.92 | 6.08 / 6.62 | 5.87 / 7.02 | 5.70 / 7.41 |
| hippie | 13.26 / 13.65 | 14.29 / 11.93 | 5.69 / 6.81 | 5.05 / 5.05 | 6.62 / 6.62 | 5.23 / 5.95 | 4.88 / 6.67 | 5.79 / 6.24 |
| deathmetal | 15.45 / 15.50 | 18.15 / 14.54 | 7.00 / 6.80 | 9.39 / 7.88 | 12.13 / 10.70 | 7.33 / 8.25 | 6.47 / 6.93 | 12.22 / 8.73 |
| punk | 16.68 / 17.42 | 18.52 / 16.29 | 8.82 / 8.50 | 5.75 / 5.75 | 7.83 / 7.83 | 7.47 / 9.08 | 4.87 / 6.03 | 6.24 / 11.78 |
| classical | 14.04 / 14.66 | 15.97 / 12.66 | 6.09 / 6.73 | 15.97 / 7.50 | 18.02 / 9.03 | 6.49 / 7.21 | 5.77 / 7.47 | 7.19 / 8.19 |

Closest floors: cyberpunk light `danger/danger-bg` 4.59 and `muted`-grade
`accent-ink/bg` 4.76; classical dark pairs `on-accent/accent` 7.50 (dark ink on
gold). The only sub-4.5 value anywhere is **default light `accent-ink` on `--bg`
= 4.20**, which is byte-identical to #8's shipped tokens (accent-ink is the
link/icon color, not part of the binding floor) and was deliberately left
untouched to honor the zero-regression rule. `muted` on `--hover` is ≥ 4.28
everywhere (worst: default light).

### Deviations from the issue's reference hexes (all mood-preserving, hit AA)

- **citypop**: accents kept periwinkle; dark-mode accent brightened to
  `#6b5ce0` for white text (4.96:1). Light link/icon violet `#3a2c9e`.
- **cyberpunk**: buttons stay deep magenta `#c01a86` in **both** modes (neon
  `#ff2daa` only passes white text at ~2.4:1 — reserved for borders); dark
  `--accent-ink` is full neon cyan `#00e5ff` (12.6:1 on bg); light accent-ink is
  desaturated deep cyan `#0b7285` (4.76:1).
- **recordshop**: burnt-orange accent darkened `#d16216` → `#b34e0e` for white
  button text (5.23:1); light accent-ink dark amber `#8d5808` (5.11:1).
- **hippie**: terracotta accent darkened `#d7573b` → `#bc4a2e` (5.05:1); light
  accent-ink muted-teal `#3f6b6e` (5.37:1).
- **deathmetal**: blood red `#8e0f1e` (light) / `#a3121f` (dark) buttons, white
  text ≥ 7.9:1; sickly-green `--accent-ink` `#8fc168` only in dark (light keeps
  blood-red links).
- **punk**: album red `#c81d1d` kept (5.75:1); light accent-ink = dark acid
  green `#2e6e1c` (5.62:1, neon `#74e85c` reserved for dark); near-black `--border`
  `#1e1b16` in light for the bold zine look.
- **classical**: light = navy `#14213d` buttons (white text 15.97:1); dark =
  gold `#d4a92e` buttons with **dark-navy ink** `#1a1e2e` on-accent (7.50:1,
  hover brightens to `#e0bc4a`); light accent-ink darkened gold `#6f530f`.
- **Component fix**: `.rec-spun` now uses `--accent-ink` instead of
  `--accent-dark` (accent-dark-as-text was 2.75:1 on dark surfaces); tokens
  themselves are unchanged for every palette.
- Default palette tokens are byte-identical to #8 (verified, plus default
  ratios above match #8's recorded 4.58/4.92/5.31/5.84 figures).