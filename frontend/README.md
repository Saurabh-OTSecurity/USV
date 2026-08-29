# Tribastion Site USV — Frontend (Phase 0, Story Point 6)

Angular application shell: login, session/token handling, route guards, and
a navigable shell with placeholder screens. No real dashboard/site/usv/
integration/user-management content yet — that's Story Point 7. This
project was generated with Angular CLI 19.2.27.

## Prerequisites

- Node.js and npm (Angular 19 warns on Node versions other than its
  officially supported range, but runs fine on reasonably recent Node 24)
- The backend running and reachable at `http://localhost:8000` (see
  `backend/README.md`) — the frontend talks to it directly over HTTP via
  `app/core/config.ts`'s `API_BASE_URL`. It never talks to PostgreSQL.

## Development server

```bash
npm install
ng serve
```

Then open `http://localhost:4200`. You'll land on `/login`; log in with any
of the six seeded backend users (see `backend/README.md`).

## Building

```bash
ng build
```

## Tests

```bash
ng test --watch=false --browsers=ChromeHeadless
```

(Requires a local Chrome install; set `CHROME_BIN` if Karma can't find it
automatically.) Covers: `AuthService` login success/failure session state,
the auth interceptor's header-attachment and 401-handling behavior, and
both route guards.

## Token storage

The token and minimal user profile are stored in **`sessionStorage`**, not
`localStorage`. Tradeoff, deliberately chosen:

- **Why `sessionStorage`**: it's cleared automatically when the tab/browser
  closes, which bounds how long a token can be replayed from browser
  storage if it's ever read out via XSS or left on a shared machine —
  there's no risk of a token quietly surviving for days in
  `localStorage` after the user thinks they're done.
- **The cost**: no persistence across tabs or browser restarts — closing
  the tab (or the browser) means logging in again. For an internal OT
  security operations tool where sessions are typically one continuous
  shift rather than "leave it open for a week," this tradeoff was judged
  worth it over `localStorage`'s convenience.
- Neither option is immune to XSS (a script running on the page can read
  either) — this is standard for browser-stored bearer tokens in general;
  it is not a substitute for the app being free of XSS vulnerabilities.

## Route guards are a UX convenience only

`auth.guard.ts` and `role.guard.ts` exist to keep a user from landing on a
screen that's about to fail (or, for `/users`, a screen they were never
going to be allowed to use) — nothing more. **The actual security boundary
is the backend's own token/role enforcement** (`core/security.py` +
`core/rbac.py`'s `get_current_user`/`require_role`, wired to every
protected route in Story Points 2-4). Every request still goes through
that server-side check regardless of what these guards decide client-side;
a user who bypasses the guard (e.g. by hitting the API directly) gets
exactly the same 401/403 the backend would always give them. This is also
stated as a code comment at the top of both guard files.

## Architecture notes

- `core/auth/` — `AuthService` (login/logout/session state via Angular
  signals), `auth.interceptor.ts` (attaches `Authorization: Bearer <token>`
  to every request except login; clears the session and redirects to
  `/login` on any 401), `auth.guard.ts`, `role.guard.ts`.
- `layout/shell.component.ts` — top header (identity/role/logout) + left
  nav (Users link only for `usv_platform_admin`), shown only once
  authenticated. On load it calls `GET /api/v1/auth/me` to re-validate the
  stored token against the backend — this is what lets a stale/tampered/
  expired token actually get caught (and cleared, via the interceptor)
  by a real request rather than just being unit-tested in isolation.
- `features/*` — one placeholder component per future screen (dashboard,
  site, usv, integrations, users), each rendering just a heading and a
  "content in Story Point 7" note.

## Additional Angular CLI resources

For more on the Angular CLI itself, see the
[Angular CLI Overview and Command Reference](https://angular.dev/tools/cli).
