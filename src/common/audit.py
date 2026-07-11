# noqa: WPS202
from pydantic import BaseModel
from enum import StrEnum
import pytest

AUTH_SERVICE_NAME = "auth-service"

# агент для тестов
TEST_USER_AGENT = "python-httpx/0.28.1"

class ErrorCode(StrEnum):
    """Перечисление кодов ошибок"""
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    INVALID_SCOPE = "INVALID_SCOPE"
    INVALID_GRANT_TYPE = "INVALID_GRANT_TYPE"
    SERVICE_NOT_FOUND = "SERVICE_NOT_FOUND"
    CLIENT_INACTIVE = "CLIENT_INACTIVE"
    INVALID_SECRET = "INVALID_SECRET"
    VAULT_SECRET_NOT_FOUND = "VAULT_SECRET_NOT_FOUND"
    EMPTY_LOGIN_REQUEST = "EMPTY_LOGIN_REQUEST"
    PERM_DENIED_SPACE="PERM_DENIED_SPACE"
    WRITE_FAILED_DUE_TO_INVALID_INPUT="WRITE_FAILED_DUE_TO_INVALID_INPUT"
    USER_NOT_FOUND="USER_NOT_FOUND"
    RESOURCE_ALREADY_EXISTS_OR_NOT_FOUND = "RESOURCE_ALREADY_EXISTS_OR_NOT_FOUND"
    NO_TUPLES_TO_WRITE_OR_DELETE = "NO_TUPLES_TO_WRITE_OR_DELETE"

class Operation(StrEnum):
    """Перечисление операций"""
    AUTH_SERVICE_CHECK_TOKEN = "auth-service.check_token"
    AUTH_SERVICE_LOGIN = "auth-service.login"
    AUTH_SERVICE_LOGIN_WITH_CLIENT_CREDENTIALS = "auth-service.loginWithClientCredentials"
    POLITICS_FILTER_NOTES="politics.filter_notes"
    FGA_UPDATE_RESOURCE="fga.update_resource"

class Level(StrEnum):
    """Перечисление уровней событий"""
    DEBUG = "debug"
    INFO = "info" # noqa: WPS110 # стандартное значение для уровня ошибки
    WARN = "warn"
    ERROR = "error"
    PANIC = "panic"

class Message(StrEnum):
    """Перечисление сообщений ошибок"""
    FAILED_TO_VALIDATE_TOKEN = "failed to validate token"
    UNKNOWN_SERVICE_CLIENT = "unknown service client. Service client not found (invalid client_id?)"
    EMPTY_LOGIN_REQUEST = "got empty body in login request"
    INVALID_TOKEN = "invalid token"
    INVALID_CLIENT = "invalid client"
    INACTIVE_CLIENT="client is inactive"
    INVALID_CLIENT_SECRET="invalid client secret"
    NOT_FOUND_VAULT_SECRET="vault secret not found"
    USER_IS_NOT_MEMBER="user is not member"
    NO_PREFIX_BEARER="invalid token: no prefix Bearer"

class Status(StrEnum):
    """Перечисление статусов событий"""
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

class Kind(StrEnum):
    """Перечисление типов событий"""
    VALIDATION = "validation"
    DOMAIN = "domain"
    INFRASTRUCTURE = "infra"
    EXTERNAL = "external"
    INTERNAL = "internal"


class AuditMessage(BaseModel):
    """Сообщение для аудита"""
    service_name: str
    level: Level
    message: str | None = None
    error_code: str | None = None
    trace_id: str | None = None
    request_id: str | None = None
    user_id: str | None = None
    stack_trace: str | None = None
    context: dict | None = None
    version: str | None = None
    current_time: str | None = None
    cause: str | None = None
    kind: Kind | None = None
    operation: str | None = None
    status: Status | None = None

def assert_audit_message(expected_audit_message: AuditMessage, real_message: AuditMessage) -> None: # noqa: WPS218 # из-за того, что есть поле со временем и другие поля, которые мы заранее не знаем, нельзя сравнить целое сообщение
    """
    Проверяет сообщение аудита на соответствие ожидаемому.
    Не проверяет: контекст, stack trace и время.
    """
    assert expected_audit_message.service_name == real_message.service_name, f"invalid service name: expected {expected_audit_message.service_name} but got {real_message.service_name}"
    assert expected_audit_message.level == real_message.level, f"invalid level: expected {expected_audit_message.level} but got {real_message.level}"
    assert expected_audit_message.error_code == real_message.error_code, f"invalid error code: expected {expected_audit_message.error_code} but got {real_message.error_code}"
    assert expected_audit_message.cause == real_message.cause, f"invalid cause: expected {expected_audit_message.cause} but got {real_message.cause}"
    assert expected_audit_message.kind == real_message.kind, f"invalid kind: expected {expected_audit_message.kind} but got {real_message.kind}"
    assert expected_audit_message.operation == real_message.operation, f"invalid operation: expected {expected_audit_message.operation} but got {real_message.operation}"
    assert expected_audit_message.status == real_message.status, f"invalid status: expected {expected_audit_message.status} but got {real_message.status}"
    assert expected_audit_message.user_id == real_message.user_id, f"invalid user id: expected {expected_audit_message.user_id} but got {real_message.user_id}"
    assert expected_audit_message.message == real_message.message, f"invalid message: expected {expected_audit_message.message} but got {real_message.message}"
    assert expected_audit_message.version == real_message.version, f"invalid version: expected {expected_audit_message.version} but got {real_message.version}"


    assert expected_audit_message.version == real_message.version, f"invalid version: expected {expected_audit_message.version} but got {real_message.version}"

def assert_audit_message_context(expected_audit_message: AuditMessage, real_message: AuditMessage) -> None:
    """
    Проверяет контекст сообщения аудита на соответствие ожидаемому.
    """
    if not expected_audit_message.context:
        return

    real_ctx = real_message.context
    if not real_ctx:
       pytest.fail("real message does not have context (empty context)")

    for key, ctx_value in expected_audit_message.context.items():    
        assert key in real_ctx, f"not found key {key} in real context"
        assert real_ctx[key] == ctx_value, f"key {key} - expected {ctx_value} but got {real_ctx[key]}"
