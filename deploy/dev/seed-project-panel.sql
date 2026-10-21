-- Pinned Remnawave 3.4.5 local stand: authorize the public development JWT only.
-- No synthetic panel users or nodes; the project will provision its own service identities.
INSERT INTO api_tokens (uuid, name, scopes, expire_at)
VALUES (
    '30000000-0000-4000-8000-000000000001',
    'my_vps_obj local development token',
    ARRAY['*'],
    now() + interval '99999 days'
)
ON CONFLICT (uuid) DO NOTHING;
