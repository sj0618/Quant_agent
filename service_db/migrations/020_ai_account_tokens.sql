-- Per-account API tokens carrying a request quota.
--
-- The shared Azure OpenAI deployment has finite capacity, so a single account running a
-- script can starve every other user. A token is the unit a quota attaches to, rather
-- than the account itself, so one account can later hold several tokens with different
-- allowances (a low one for an automation, a normal one for interactive use) without a
-- schema change.

CREATE TABLE IF NOT EXISTS app.ai_account_token (
    token_id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES app.users(user_id),
    label TEXT,
    -- Leading characters of the raw token, kept in the clear purely so a management UI
    -- can tell two tokens apart. Far too short to narrow a search for the secret.
    token_prefix TEXT NOT NULL,
    -- Only the SHA-256 digest of the token is stored, never the token. A slow password
    -- KDF would buy nothing here: the secret is high-entropy random bytes, not a human
    -- password, so it is not guessable at any hash speed - and this digest is computed
    -- on every authenticated request, where the added latency would be real.
    token_hash TEXT NOT NULL UNIQUE,
    quota_limit INTEGER NOT NULL CHECK (quota_limit > 0),
    quota_window_seconds INTEGER NOT NULL DEFAULT 60 CHECK (quota_window_seconds > 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ai_account_token_user_created
    ON app.ai_account_token (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_account_token_status
    ON app.ai_account_token (status);
