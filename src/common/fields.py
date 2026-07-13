from enum import StrEnum

# FIELDS
ERROR_FIELD = "error"
MESSAGE_FIELD = "message"
TOKEN_TYPE_FIELD = "token_type"
EXPIRES_IN_FIELD = "expires_in"
SCOPE_FIELD = "scope"
USER_AGENT_FIELD = "user_agent"
USER_ID_FIELD = "user_id"
GRANT_TYPE_FIELD = "grant_type"
CLIENT_ID_FIELD = "client_id"
TOKEN_PAYLOAD_FIELD = "token_payload"

# AUTH FIELDS
GRANT_TYPE_CLIENT_CREDENTIALS = "client_credentials"
GRANT_TYPE_PASSWORD = "password"
CLIENT_ID_BOT = "bot"
SCOPE_BOT = "bot"
SCOPE_ADMIN = "admin"
SUBJECT_BOT = "bot"
SUBJECT_ADMIN = "admin"
AUDIENCE_INTERNAL_API = "zanuda-internal-api"
ISSUER_AUTH_SERVICE = "zanuda-auth-service"

# VAULT BUNDLES
VAULT_SECRET_BUNDLE = "vault"
WRONG_SECRET_BUNDLE = "wrong"
NO_VAULT_SECRET_BUNDLE = "no_vault"

# NOTES FIELDS
NOTE_IDS_FIELD = "note_ids"
SPACE_ID_FIELD = "space_id"
NOTES_FIELD = "notes"
CAN_READ_FIELD = "can_read"
CAN_EDIT_FIELD = "can_edit"

# UPDATE RESOURCE FIELDS
NOTES_SERVICE_NAME = "notes-service"
class ResourceType(StrEnum):
    NOTE = "note"
    SPACE = "space"
    USER = "user"

class Relation(StrEnum):
    OWNER = "owner"
    SPACE = "space"

class Operation(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

class ChangeType(StrEnum):
    RESOURCE_ADDED = "resource_added"
    RESOURCE_UPDATED = "resource_updated"
    RESOURCE_DELETED = "resource_deleted"
    MEMBERSHIP_ADDED = "membership_added"
    MEMBERSHIP_REMOVED = "membership_removed"
    MEMBERSHIP_CHANGED = "membership_changed"

class Status(StrEnum):
    COMPLETED = "completed"
    ERROR = "error"

class OperationResult(StrEnum):
    APPLIED = "applied"
    FAILED = "failed"

class EventType(StrEnum):
    NOTE_CREATED = "NOTE_CREATED"