# Architecture Decisions

## Layered architecture

Every endpoint follows the same layering, and route handlers never touch
SQLAlchemy or the database directly:

```
API route (app/api/routes/*.py)
    -> Service (app/services/*.py)
        -> Repository (app/repositories/*.py)
            -> SQLAlchemy model / Session (app/models/*.py, app/core/database.py)
                -> PostgreSQL
```

- **Routes** parse/validate the request (via Pydantic schemas in
  `app/schemas/`), resolve dependencies (`get_current_user`, `require_role`,
  `get_db`), call exactly one service method, and shape the HTTP response.
  They contain no queries.
- **Services** hold business logic/orchestration — e.g. `AuthService.login`
  verifies the password, updates `last_login_at`, issues a token, *and*
  writes the `audit_log` row, so a route never has to remember to do all of
  that itself. Services call one or more repositories.
- **Repositories** are the only layer that issues SQLAlchemy queries. Each
  repository is scoped to one model (`SiteRepository`, `UsvRepository`,
  `IntegrationRepository`, `UsvUserRepository`, `AuditLogRepository`) and
  exposes plain methods (`list_all`, `get_by_id`, `create`, ...) with no
  HTTP or business-logic awareness.

Centralized exception handling lives in `app/main.py` (handlers for
`HTTPException` and `RequestValidationError`, plus an HTTP middleware for
any other unhandled `Exception`), so every layer above the route can just
raise/let-propagate and the JSON error shape (`{"error": {"code",
"message"}}`) stays consistent everywhere without each route
reimplementing it.

**Gotcha (found during Story Point 7 frontend validation):** the
catch-all handler is a plain `@app.middleware("http")`, not
`@app.exception_handler(Exception)`. FastAPI/Starlette special-case a
handler registered for the bare `Exception` type by attaching it to
`ServerErrorMiddleware`, the absolute outermost layer — outside every
`add_middleware()`-registered middleware, including `CORSMiddleware`,
regardless of registration order. A response built there never passes
back through CORS, so a browser talking cross-origin to this API (as the
Angular frontend does in development) sees a bare CORS failure instead of
the actual error body. Using an HTTP middleware avoids this, but only
because it's also registered *before* `CORSMiddleware` in `main.py`:
Starlette wraps `add_middleware()` calls so the one added last ends up
outermost, so `CORSMiddleware` needs to be added after this middleware to
stay outermost and get a chance to stamp headers on the responses it
produces.

## Password hashing: bcrypt

Chosen over argon2 for continuity with Story Point 1's seed script, which
already hashes the six seed users with bcrypt (via `passlib`). `core/security.py`
uses the same `passlib.context.CryptContext(schemes=["bcrypt"])` so seed-time
and runtime hashing/verification are guaranteed identical. bcrypt is a
well-audited, widely deployed algorithm and sufficient for this platform's
threat model; there's no requirement here that specifically needs argon2's
memory-hardness tuning.

Note: `passlib`'s bcrypt backend requires `bcrypt<4.1` (pinned to `4.0.1`)
due to a known incompatibility between `passlib==1.7.4` and newer `bcrypt`
releases that removed the `__about__.__version__` attribute passlib reads.

## Token issuance: JWT (stateless), not server-side sessions

Chosen because:

- USV is one of several Tribastion components (it also talks to ECC and
  will host multiple future API consumers). A stateless, self-contained
  token avoids needing a shared session store between processes now or as
  the system grows.
- No session storage/cleanup infrastructure needs to be built in this
  story point — decoding is pure computation against a secret key.
- The FastAPI dependency layer required here (`get_current_user`,
  `require_role`) maps naturally onto decoding a bearer token per request.

Implementation: `PyJWT`, algorithm `HS256`, secret from `AUTH_SECRET_KEY`
(environment variable, never hard-coded), expiry from
`AUTH_TOKEN_EXPIRY_MINUTES` (environment variable). Token payload carries
`user_id`, `role`, `site_id` (nullable, for platform-scoped accounts),
`iat`, and `exp`. `usv_user.status` is still checked against the database
on every request in `get_current_user`, so deactivating a user takes
effect immediately even though the token itself is stateless and can't be
individually revoked before its expiry.

## Logout: client-side token discard only

`POST /api/v1/auth/logout` does **not** perform server-side token
revocation. Because tokens are stateless JWTs with no revocation list or
session store in this phase, a token that has already been issued remains
cryptographically valid, and would still be accepted by `get_current_user`,
until it naturally expires (`AUTH_TOKEN_EXPIRY_MINUTES` after issuance) —
even after the client calls `/logout`. The endpoint exists for API
symmetry and to make the client's responsibility explicit (discard the
token locally), and this limitation is intentional for Phase 0, not an
oversight. Keeping `AUTH_TOKEN_EXPIRY_MINUTES` short bounds how long a
"logged out" token stays technically usable. A real revocation list (e.g.
a denylist table or a move to server-side sessions) would be needed before
this is acceptable for a deployment requiring immediate logout guarantees.
