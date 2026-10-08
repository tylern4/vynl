# #4: Frontend foundation — scaffold, API client, auth, routing, theme

- **Status:** open
- **Assignee:** unassigned
- **Labels:** frontend, foundation
- **Depends on:** none
- **Wave:** 1 (runs in parallel with #1; touches only `frontend/`)

## Summary

Stand up the React + TypeScript + Vite frontend in the style of
[baby-tracking-app](https://github.com/tylern4/baby-tracking-app): build/dev setup,
nginx production config, typed API client, auth context + login/register pages,
router with protected routes, theme (light/dark) system, and the shared types that
issues #5/#6 will build pages on.

## Acceptance criteria

- [ ] `frontend/package.json` — scripts `dev`, `build` (`tsc -b && vite build`),
      `preview`, `test` (`vitest run`); deps: `react`, `react-dom`,
      `react-router-dom`, `lucide-react`; dev deps mirroring the reference
      (`vite`, `vitest`, `@vitejs/plugin-react`, `typescript`, `jsdom`,
      `@testing-library/{react,user-event,jest-dom,dom}`, `@types/react{,-dom}`).
      Runs `npm install` successfully (commit `package-lock.json`).
- [ ] `vite.config.ts` — dev server port 5173 with `/api` →
      `http://localhost:8000` proxy; vitest config: jsdom,
      `src/test/setup.ts`, `css: false`.
- [ ] `tsconfig.json` strict, `index.html`, `src/main.tsx`.
- [ ] `src/types.ts` — TypeScript types for every PLAN §5 response shape:
      `User`, `SearchResult`, `Album`, `Track`, `Tag`, `Play`,
      `TrackSearchResult`, `Recommendation` (nullable fields explicitly typed).
- [ ] `src/api.ts` — `request<T>` wrapper identical in behavior to the reference:
      `/api` prefix, JSON, Bearer token from `localStorage` key `vynl_token`,
      `ApiError` with status, 401 → clear token + redirect `/login`, 204 →
      undefined. Export an `api` object with **auth calls implemented**
      (`register`, `login`, `me`) and stubs/list-methods for the §5 endpoints
      (#5 fills the rest): `searchAlbums`, `importAlbum`, `listAlbums`,
      `getAlbum`, `updateAlbum`, `deleteAlbum`, `getCoverUrl(id)`, `getTags`,
      `createTag`, `setAlbumTags`, `logPlay`, `listPlays`, `deletePlay`,
      `searchTracks`, `getRecommendations`.
- [ ] `src/auth.tsx` — `AuthProvider` + `useAuth` (loads `/auth/me` on mount,
      `login/logout/setToken`), `ProtectedRoute` redirecting to `/login`.
- [ ] `src/pages/Login.tsx`, `src/pages/Register.tsx` — same flows/UX as the
      reference (name/email/password/invite code, error display, pending-account
      message, link between the two pages).
- [ ] `src/App.tsx` — router with `/login`, `/register`, and placeholder routes
      for `/` (Shelf), `/album/:id`, `/add`, `/find`, `/recommend` (simple stub
      components importing nothing heavy — #5/#6 replace them), top bar with
      app name **vynl**, nav links, theme toggle, logout.
- [ ] `src/theme.tsx` — dark/light context, persisted to `localStorage`,
      defaults to system preference (reference behavior); `styles.css` with CSS
      variables for both themes covering basics (background, surface, text,
      border, accent, radius, spacing) + simple responsive container.
- [ ] `nginx.conf` + `Dockerfile` copied from reference semantics: multi-stage
      node:20-alpine build → nginx:1.27-alpine, `/api/` proxy to
      `backend:8000`, `index.html` no-cache, `/assets/` immutable, SPA
      `try_files … /index.html`.
- [ ] Tests: `src/api.test.ts` (token handling, error mapping, 401 redirect),
      `src/App.test.tsx` (renders login when logged out, redirects protected
      routes), `src/pages/Login.test.tsx`, `Register.test.tsx`,
      `theme.test.tsx`. `npm test` and `npm run build` both pass.

## Notes

- Reference frontend is the style guide: `frontend/src/{api.ts,auth.tsx,theme.tsx,
  App.tsx,pages/Login.tsx,pages/Register.tsx,styles.css}`, `vite.config.ts`,
  `nginx.conf`, `Dockerfile`.
- Types must match PLAN §5 exactly — #5 builds views against them; a mismatch
  blocks the wave.
- Do not build shelf/detail/find/recommend UIs (#5, #6).
