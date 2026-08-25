# Google Auth Backend Implementation Notes

## Summary

This backend implements a production-oriented Google OAuth login flow for QuantAgent.
The server owns the OAuth callback, persists the authenticated user in PostgreSQL,
stores the browser session in Redis, and serves a minimal same-origin `/login` and `/app`
HTML surface.

## User flow

1. User opens `/login`.
2. The login page starts Google auth through `GET /auth/google/start?return_to=/app`.
3. Google redirects back to `GET /auth/google/callback`.
4. The backend validates OAuth state, nonce, and Google identity.
5. The backend upserts the Google user into `app.users`.
6. The backend creates a Redis-backed session and sets the `qa_session` HTTP-only cookie.
7. The callback redirects to `/app`.
8. `/app` calls `GET /auth/me` to load the logged-in profile.

## Main backend files

- `app/api/routes/auth.py`
  - Google OAuth start and callback endpoints.
  - `/auth/me`, `/auth/csrf`, and `/auth/logout`.
- `app/api/routes/pages.py`
  - Serves `/login` and `/app`.
  - Redirects unauthenticated users from `/app` to `/login`.
- `app/services/google_oauth.py`
  - Builds Google authorization URLs.
  - Exchanges authorization codes.
  - Validates Google ID token claims.
- `app/services/session_store.py`
  - Stores OAuth state, sessions, and CSRF tokens in Redis.
- `app/db/user_queries.py`
  - Inspects `app.users` schema.
  - Upserts and loads Google users.
- `app/db/session.py`
  - Creates async SQLAlchemy engines.
  - Runs DB reads and write-returning statements.

## `app.users` schema compatibility

The deployed database uses `user_id` as the user primary key column, while the auth API
returns a public `id` field to the frontend.

The backend now supports either column name:

- `id`
- `user_id`

When the database has `user_id`, SQL maps it to the API shape with:

```sql
CAST(user_id AS text) AS id
```

This keeps the database schema unchanged while preserving the frontend/session contract
that expects `user.id`.

Required Google identity binding columns:

- `email`
- `auth_provider`
- `provider_user_id`

Required uniqueness:

- unique or primary-key-compatible constraint covering `(auth_provider, provider_user_id)`

## Fixes implemented

### 1. `user_id` to `id` mapping

The first login failure happened because the code expected an `id` column, but the
database table had `user_id`.

Fix:

- Accept `id` or `user_id` as the canonical user identifier column.
- Return `CAST(user_id AS text) AS id` when `user_id` is present.
- Load `/auth/me` users with `WHERE CAST(user_id AS text) = :user_id`.

### 2. `/auth/me` after callback returned unauthorized

Google callback returned `303`, but `/auth/me` returned `401` and the browser returned to
`/login`.

Root cause:

- The upsert path used `INSERT ... RETURNING`, but the DB helper did not run write
  statements inside a committing transaction.
- The callback could receive a returned row and create a Redis session, while the user row
  was not guaranteed to be committed for the next `/auth/me` lookup.

Fix:

- `execute_one()` now uses `async with engine.begin()` so write-returning statements commit
  on success.

## Runtime configuration

Required environment variables when auth is enabled:

```env
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_SAMESITE=lax
```

For production:

- Use HTTPS redirect URIs.
- Keep `AUTH_COOKIE_SECURE=true`.
- Configure allowed origins/hosts for the deployed backend domain.

## Verification

The backend test suite passes after the auth fixes:

```text
python -m pytest
48 passed, 6 warnings
```

Important regression coverage:

- Google callback sets a session cookie and redirects.
- Callback-created session can call `/auth/me` successfully.
- `user_id` schema maps to public `id`.
- DB write-returning statements run inside a committing transaction.

## GitHub upload guidance

To upload only the backend implementation and this document, stage only `backend/` and
the root `.gitignore` change:

```powershell
git add backend/ .gitignore
git status --short
```

Do not stage local artifacts such as:

- `.omx/`
- `omx.zip`
- `.env`
- `__pycache__/`
- `.pytest_cache/`
- `*.egg-info/`

