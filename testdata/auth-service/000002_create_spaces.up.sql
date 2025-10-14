INSERT INTO spaces.spaces (id, type, owner_id, default_participant_role) values (
    'c7adddae-4949-49e6-b57e-1aa4e8be7fdb', 'PERSONAL', '56279a7c-13a0-4464-98fe-8cee52bcd3b7', 'OWNER'
)
ON CONFLICT (id) DO UPDATE SET
    type = EXCLUDED.type,
    owner_id = EXCLUDED.owner_id,
    default_participant_role = EXCLUDED.default_participant_role;

INSERT INTO spaces.space_member (space_id, user_id, role_id, status) VALUES (
    'c7adddae-4949-49e6-b57e-1aa4e8be7fdb', '56279a7c-13a0-4464-98fe-8cee52bcd3b7', (select id from spaces.space_role where code = 'OWNER'), 'ACTIVE'
)
ON CONFLICT (space_id, user_id) DO UPDATE SET
    role_id = EXCLUDED.role_id,
    status = EXCLUDED.status;
