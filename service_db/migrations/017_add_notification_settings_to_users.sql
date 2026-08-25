-- Store user notification preferences with the user account.
-- Existing rows use the defaults; data from the legacy
-- app.user_notification_settings table is intentionally not migrated.

BEGIN;

ALTER TABLE app.users
    ADD COLUMN IF NOT EXISTS daily_report_email BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS action_emails BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS marketing_email BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS delivery_hour TEXT NOT NULL DEFAULT '08:00';

COMMIT;
