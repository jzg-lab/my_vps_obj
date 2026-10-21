-- Local development only. Known password: Minishop-Dev-2026!
-- Reuse the upstream demo password hash, but create no paid subscriptions or panel bindings.
-- Re-running the seed preserves accounts edited through the UI.
BEGIN;

INSERT INTO users (
    user_id, username, email, email_verified_at, first_name, language_code,
    is_banned, password_hash, password_set_at, telegram_notifications_status
)
SELECT user_id, username, email, now(), first_name, 'en', false,
    'pbkdf2_sha256$260000$ZGV2LW1vY2stc2FsdC12MQ$yidwfE8twrgh7F9p4vZ0grT2zjvEOGIPkSD5XEUt1Nk',
    now(), 'blocked'
FROM (VALUES
    (910000001::bigint, 'runes_admin', 'runes.admin@example.com', 'Development Admin'),
    (910000002::bigint, 'runes_active', 'runes.active@example.com', 'Development User A'),
    (910000003::bigint, 'runes_expired', 'runes.expired@example.com', 'Development User B')
) AS fixtures(user_id, username, email, first_name)
ON CONFLICT (user_id) DO NOTHING;

WITH granted AS (
    INSERT INTO account_roles (user_id, role)
    VALUES (910000001, 'owner')
    ON CONFLICT (user_id, role) DO NOTHING
    RETURNING user_id, role
)
INSERT INTO account_role_events (user_id, role, action, source)
SELECT user_id, role, 'grant', 'project_dev_seed' FROM granted;

COMMIT;
