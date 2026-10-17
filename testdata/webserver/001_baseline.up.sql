-- Fixed test keys; triggers create personal spaces for newly inserted users.
INSERT INTO users.users (tg_id, username)
VALUES (123456789, 'testkit-webserver'), (987654321, 'testkit-webserver-other')
ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username;

INSERT INTO shared_spaces.shared_spaces (id, name, created, creator, personal)
SELECT '869dc163-62aa-4889-9019-07f9c764ce38'::uuid,
       'testkit-webserver-owned', TIMESTAMP '2026-01-01', id, false
FROM users.users WHERE tg_id = 123456789
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name, creator = EXCLUDED.creator, personal = EXCLUDED.personal;

INSERT INTO shared_spaces.shared_spaces (id, name, created, creator, personal)
SELECT '6eabae90-5724-4445-84d8-510774bdee03'::uuid,
       'testkit-webserver-other', TIMESTAMP '2026-01-01', id, false
FROM users.users WHERE tg_id = 987654321
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name, creator = EXCLUDED.creator, personal = EXCLUDED.personal;
