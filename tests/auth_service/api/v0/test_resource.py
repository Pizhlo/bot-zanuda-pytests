import logging, time  
from dataclasses import asdict, dataclass
from collections.abc import Callable
from typing import ContextManager, Optional
import httpx, pytest, uuid

from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common.server_error_logging import log_internal_server_error
import src.models.resource as resource
import src.common.ids as ids 
import src.common.audit as audit 
import src.common.fields as fields
from tests.fixtures.auth_jwt import TokenFields

logger = logging.getLogger(__name__)

NOTE_CREATED_REQUEST_ID = str(uuid.uuid4())
NOTE_OWNER_ID = ids.SHARED_SPACE_OWNER_UUID
NOTE_SPACE_ID = ids.SHARED_SPACE_ID
NOTE_ID = "1776f52a-8ce0-4bcd-9b75-0d3f2606883a"

NOTE_OWNER_SUBJECT = f"{fields.ResourceType.USER}:{NOTE_OWNER_ID}"
NOTE_RESOURCE = f"{fields.ResourceType.NOTE}:{NOTE_ID}"
NOTE_SPACE_SUBJECT = f"{fields.ResourceType.SPACE}:{NOTE_SPACE_ID}"

ONE_HOUR_SECONDS = 60 * 60

SPACE_CREATED_REQUEST_ID = str(uuid.uuid4())

@dataclass(frozen=True)
class UpdateResourceCase:
    """Сценарий для вызова update_resource."""

    request: resource.ResourceChangeMessage
    expected_status_code: int
    expected_response: resource.ResourceChangeResponse | resource.ResourceChangeErrorResponse | None
    expected_message: str | None
    x_telegram_user_id: str | None


@dataclass(frozen=True)
class InvalidUpdateResourceTokenCase:
    """Сценарий негативной проверки токена для update_resource."""

    token_fields: TokenFields | None
    expected_status_code: int
    telegram_user_id: str | None
    expected_message: str | None
    expected_response: resource.ResourceChangeResponse | None


DEFAULT_UPDATE_RESOURCE_REQUEST = resource.ResourceChangeMessage(
    request_id=NOTE_CREATED_REQUEST_ID,
    resource=resource.ResourceRef(type=fields.ResourceType.NOTE, id=NOTE_ID),
    operation=fields.Operation.CREATE,
    change_type=fields.ChangeType.RESOURCE_ADDED,
    relations=resource.ResourceRelations(
        owner=resource.ResourceRef(type=fields.ResourceType.USER, id=NOTE_OWNER_ID),
        parent=resource.ResourceRef(type=fields.ResourceType.SPACE, id=NOTE_SPACE_ID),
    ),
    context=resource.ResourceEventContext(
        source_service=fields.NOTES_SERVICE_NAME,
        event_type=fields.EventType.NOTE_CREATED,
    ),
)


class TestUpdateResource:
    """
    Тесты для проверки обновления ресурса.
    Обновление ресурса — это сообщение о том, что ресурс добавлен / удалён / изменён.
    Примеры запросов: заметка создана, добавлен участник пространства, изменена роль пользователя в пространстве.
    """

    @pytest.mark.parametrize(
        ("case", "expected_audit_message"),
        [
            pytest.param(
                UpdateResourceCase(
                    x_telegram_user_id=ids.ADMIN_USER_ID,
                    request=resource.ResourceChangeMessage(
                        request_id=NOTE_CREATED_REQUEST_ID,
                        resource=resource.ResourceRef(type=fields.ResourceType.NOTE, id=NOTE_ID),
                        operation=fields.Operation.CREATE,
                        change_type=fields.ChangeType.RESOURCE_ADDED,
                        relations=resource.ResourceRelations(
                            owner=resource.ResourceRef(type=fields.ResourceType.USER, id=NOTE_OWNER_ID),
                            parent=resource.ResourceRef(type=fields.ResourceType.SPACE, id=NOTE_SPACE_ID),
                        ),
                        context=resource.ResourceEventContext(
                            source_service=fields.NOTES_SERVICE_NAME,
                            event_type=fields.EventType.NOTE_CREATED,
                        ),
                    ),
                    expected_status_code=httpx.codes.OK,
                    expected_response=resource.ResourceChangeResponse(
                        request_id=NOTE_CREATED_REQUEST_ID,
                        idempotency_key="",
                        status=fields.Status.COMPLETED,
                        operation_result=fields.OperationResult.APPLIED,
                        resource=resource.ResourceRef(type=fields.ResourceType.NOTE, id=NOTE_ID),
                        written_tuples=(
                            resource.AuthTuple(
                                subject=NOTE_OWNER_SUBJECT,
                                relation=fields.Relation.OWNER,
                                resource=NOTE_RESOURCE,
                            ),
                            resource.AuthTuple(
                                subject=NOTE_SPACE_SUBJECT,
                                relation=fields.Relation.SPACE,
                                resource=NOTE_RESOURCE,
                            ),
                        ),
                        deleted_tuples=(),
                        meta=resource.ResourceChangeMeta(),
                    ),
                    expected_message=None,
                ),
                None, # для успешных кейсов нет аудит сообщений
                id="note created",
            ),
             pytest.param(
                UpdateResourceCase(
                    x_telegram_user_id=ids.ADMIN_USER_ID,
                    request=resource.ResourceChangeMessage(
                        request_id=NOTE_CREATED_REQUEST_ID,
                        resource=resource.ResourceRef(type="note", id=NOTE_ID),
                        operation="create",
                        change_type="resource_added",
                        relations=resource.ResourceRelations(
                            owner=resource.ResourceRef(type="user", id=NOTE_OWNER_ID),
                            parent=resource.ResourceRef(type="space", id=NOTE_SPACE_ID),
                        ),
                        context=resource.ResourceEventContext(
                            source_service=fields.NOTES_SERVICE_NAME,
                            event_type=fields.EventType.NOTE_CREATED,
                        ),
                    ),
                    expected_status_code=httpx.codes.CONFLICT,
                    expected_response=resource.ResourceChangeErrorResponse(
                        request_id=NOTE_CREATED_REQUEST_ID,
                        status=fields.Status.ERROR,
                        operation_result=fields.OperationResult.FAILED,
                        resource=resource.ResourceRef(type=fields.ResourceType.NOTE, id=NOTE_ID),
                        error=resource.ResourceChangeError(
                            code=audit.ErrorCode.RESOURCE_ALREADY_EXISTS_OR_NOT_FOUND,
                            message="new resource already exists or deleted resource not found",
                            details=resource.ResourceChangeErrorDetails(operation=fields.Operation.CREATE),
                        ),
                        meta=resource.ResourceChangeMeta(),
                    ),
                    expected_message=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.ERROR,
                    cause=(
                        f'POST validation error for Write POST with body {{"code":"write_failed_due_to_invalid_input",'
                        f'"message":"cannot write a tuple which already exists: user: \'user:{NOTE_OWNER_ID}\', relation: \'owner\', object: \'note:{NOTE_ID}\': tuple to be written already existed or the tuple to be deleted did not exist"}}\n'
                        f" with error code write_failed_due_to_invalid_input error message: cannot write a tuple which already exists: user: 'user:{NOTE_OWNER_ID}', relation: 'owner', object: 'note:{NOTE_ID}': tuple to be written already existed or the tuple to be deleted did not exist"
                    ),
                    error_code=audit.ErrorCode.WRITE_FAILED_DUE_TO_INVALID_INPUT,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.FGA_UPDATE_RESOURCE,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, fields.USER_ID_FIELD: ids.ADMIN_USER_ID},
                ),
                id="note already exists",
            ),
             pytest.param(
                UpdateResourceCase(
                    x_telegram_user_id=ids.INVALID_USER_ID,
                    request=resource.ResourceChangeMessage(
                        request_id=NOTE_CREATED_REQUEST_ID,
                        resource=resource.ResourceRef(type=fields.ResourceType.NOTE, id=NOTE_ID),
                        operation=fields.Operation.CREATE,
                        change_type=fields.ChangeType.RESOURCE_ADDED,
                        relations=resource.ResourceRelations(
                            owner=resource.ResourceRef(type=fields.ResourceType.USER, id=NOTE_OWNER_ID),
                            parent=resource.ResourceRef(type=fields.ResourceType.SPACE, id=NOTE_SPACE_ID),
                        ),
                        context=resource.ResourceEventContext(
                            source_service=fields.NOTES_SERVICE_NAME,
                            event_type=fields.EventType.NOTE_CREATED,
                        ),
                    ),
                    expected_status_code=httpx.codes.NOT_FOUND,
                    expected_response=resource.ResourceChangeErrorResponse(
                        request_id=NOTE_CREATED_REQUEST_ID,
                        status=fields.Status.ERROR,
                        operation_result=fields.OperationResult.FAILED,
                        resource=resource.ResourceRef(type=fields.ResourceType.NOTE, id=NOTE_ID),
                        error=resource.ResourceChangeError(
                            code=audit.ErrorCode.USER_NOT_FOUND,
                            message="user not found",
                            details=resource.ResourceChangeErrorDetails(operation=fields.Operation.CREATE),
                        ),
                        meta=resource.ResourceChangeMeta(),
                    ),
                    expected_message=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.ERROR,
                    cause="not found",
                    error_code=audit.ErrorCode.USER_NOT_FOUND,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.FGA_UPDATE_RESOURCE,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, fields.USER_ID_FIELD: ids.INVALID_USER_ID},
                ),
                id="user not found",
            ),
             pytest.param(
                UpdateResourceCase(
                    x_telegram_user_id=ids.ADMIN_USER_ID,
                    request=resource.ResourceChangeMessage(
                        request_id=NOTE_CREATED_REQUEST_ID,
                        resource=resource.ResourceRef(type=fields.ResourceType.NOTE, id=NOTE_ID),
                        operation=fields.Operation.CREATE,
                        change_type=fields.ChangeType.RESOURCE_ADDED,
                        relations=None,
                        context=resource.ResourceEventContext(
                            source_service=fields.NOTES_SERVICE_NAME,
                            event_type=fields.EventType.NOTE_CREATED,
                        ),
                    ),
                    expected_status_code=httpx.codes.BAD_REQUEST,
                    expected_response=resource.ResourceChangeErrorResponse(
                        request_id=NOTE_CREATED_REQUEST_ID,
                        status=fields.Status.ERROR,
                        operation_result=fields.OperationResult.FAILED,
                        resource=resource.ResourceRef(type=fields.ResourceType.NOTE, id=NOTE_ID),
                        error=resource.ResourceChangeError(
                            code=audit.ErrorCode.NO_TUPLES_TO_WRITE_OR_DELETE,
                            message="no tuples to write or delete",
                            details=resource.ResourceChangeErrorDetails(operation=fields.Operation.CREATE),
                        ),
                        meta=resource.ResourceChangeMeta(),
                    ),
                    expected_message=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.ERROR,
                    cause="no tuples to write or delete",
                    error_code=audit.ErrorCode.WRITE_FAILED_DUE_TO_INVALID_INPUT,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.FGA_UPDATE_RESOURCE,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, fields.USER_ID_FIELD: ids.ADMIN_USER_ID},
                ),
                id="no tuples to write or delete",
            ),
        ],
    )
    def test_create_note(
        self,
        case: UpdateResourceCase,
        login: str,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """
        Тест на создание заметки.
        - Успешное создание заметки: 200 OK
        - Заметка уже существует: 409 Conflict
        - Пользователя не существует (хедер x-telegram-user-id): 404 Not Found
        - Нет корректных данных для записи: 400 Bad Request
        """
        token = login

        response = auth_service_v0_api_client.update_resource(asdict(case.request), token=token, x_telegram_user_id=case.x_telegram_user_id)
        log_internal_server_error(response, logger, fields.ERROR_FIELD)
        assert response.status_code == case.expected_status_code, response.text

        if case.expected_message is not None:
            assert response.json()[fields.ERROR_FIELD] == case.expected_message

        if case.expected_response is not None:
            resource.assert_api_response(response.json(), case.expected_response)
        
        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        if message and expected_audit_message is not None:
            real_message = audit.AuditMessage.model_validate_json(message)
            audit.assert_audit_message(expected_audit_message, real_message)
            audit.assert_audit_message_context(expected_audit_message, real_message)
        elif expected_audit_message is not None:
            pytest.fail("No audit messages in queue")

    @pytest.mark.parametrize(
        ("invalid_case", "expected_audit_message"),
        [
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub=fields.SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) - ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=audit.Message.INVALID_TOKEN,
                    expected_response=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.WARN,
                    message=audit.Message.FAILED_TO_VALIDATE_TOKEN,
                    cause="token has invalid claims: token is expired",
                    error_code=audit.ErrorCode.AUTH_TOKEN_EXPIRED,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.AUTH_SERVICE_CHECK_TOKEN,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT},
                ),
                id="expired token",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=None,
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message="invalid token: no prefix Bearer",
                    expected_response=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.WARN,
                    message=audit.Message.NO_PREFIX_BEARER,
                    error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
                    cause="invalid token: no prefix Bearer",
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.AUTH_SERVICE_CHECK_TOKEN,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT},
                ),
                id="no token",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message="invalid token: invalid client id",
                    expected_response=None,
                ),
                None,
                id="token without sub",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub=fields.SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                expected_message=audit.Message.INVALID_TOKEN,
                    expected_response=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.WARN,
                    message=audit.Message.FAILED_TO_VALIDATE_TOKEN,
                    cause="token has invalid claims: token is missing required claim: iss claim is required",
                    error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.AUTH_SERVICE_CHECK_TOKEN,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT},
                ),
                id="token without iss",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub=fields.SUBJECT_BOT,
                        iat=int(time.time()),
                        scope=fields.SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                expected_message=audit.Message.INVALID_TOKEN,
                    expected_response=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.WARN,
                    message=audit.Message.FAILED_TO_VALIDATE_TOKEN,
                    cause="token has invalid claims: token is missing required claim: exp claim is required",
                    error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.AUTH_SERVICE_CHECK_TOKEN,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT},
                ),
                id="token without exp",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub=fields.SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message="invalid token: invalid scope",
                    expected_response=None,
                ),
                None,
                id="token without scope",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        sub=fields.SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                expected_message=audit.Message.INVALID_TOKEN,
                    expected_response=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.WARN,
                    message=audit.Message.FAILED_TO_VALIDATE_TOKEN,
                    cause="token has invalid claims: token is missing required claim: aud claim is required",
                    error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.AUTH_SERVICE_CHECK_TOKEN,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT},
                ),
                id="token without aud",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub=fields.SUBJECT_BOT,
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                expected_message=audit.Message.INVALID_TOKEN,
                    expected_response=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.WARN,
                    message=audit.Message.FAILED_TO_VALIDATE_TOKEN,
                    cause="token is missing required claim: iat claim is required",
                    error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.AUTH_SERVICE_CHECK_TOKEN,
                    status=audit.Status.FAILED,
                    context={"iat": "iat claim is required", fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT},
                ),
                id="token without iat",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub=fields.SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=(
                        "invalid request: header 'X-Telegram-User-Id' not found"
                    ),
                    expected_response=None,
                ),
                None,
                id="no x-telegram-user-id",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub=fields.SUBJECT_ADMIN,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                expected_message=audit.Message.INVALID_CLIENT,
                    expected_response=None,
                ),
                None,
                id="invalid client",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss="zanuda-other-service",
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub=fields.SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                expected_message=audit.Message.INVALID_TOKEN,
                    expected_response=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.WARN,
                    message=audit.Message.FAILED_TO_VALIDATE_TOKEN,
                    cause="token has invalid claims: token has invalid issuer",
                    error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.AUTH_SERVICE_CHECK_TOKEN,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT},
                ),
                id="invalid issuer",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=["zanuda-other-api"],
                        sub=fields.SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                expected_message=audit.Message.INVALID_TOKEN,
                    expected_response=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.WARN,
                    message=audit.Message.FAILED_TO_VALIDATE_TOKEN,
                    cause="token has invalid claims: token has invalid audience",
                    error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.AUTH_SERVICE_CHECK_TOKEN,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT},
                ),
                id="invalid aud",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub=fields.SUBJECT_BOT,
                        iat=int(time.time()) + ONE_HOUR_SECONDS,
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=audit.Message.INVALID_TOKEN,
                    expected_response=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.WARN,
                    message="failed to validate token",
                    cause="token has invalid claims: token used before issued",
                    error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.AUTH_SERVICE_CHECK_TOKEN,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT},
                ),
                id="invalid iat",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub=fields.SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_ADMIN,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message="client does not have required scope",
                    expected_response=None,
                ),
                None,
                id="invalid scope",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub="bot2",
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_ADMIN,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=audit.Message.INVALID_CLIENT,
                    expected_response=None,
                ),
                None,
                id="invalid client id",
            ),
            pytest.param(
                InvalidUpdateResourceTokenCase(
                    token_fields=TokenFields(
                        iss=fields.ISSUER_AUTH_SERVICE,
                        aud=[fields.AUDIENCE_INTERNAL_API],
                        sub="bot2",
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=fields.SCOPE_ADMIN,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=ids.RANDOM_INVALID_USER_ID,
                    expected_message=audit.Message.INVALID_CLIENT,
                    expected_response=None,
                ),
                None,
                id="invalid client id with telegram user",
            ),
        ],
    )
    def test_update_resource_invalid_token(
        self,
        invalid_case: InvalidUpdateResourceTokenCase,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        jwt_token_factory: Callable[..., str],
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """
        Тест на обновление ресурса.
        - Протухший токен - 401
        - Токена нет - 401
        - В токене нет sub - 401
        - В токене нет iss - 401
        - В токене нет exp - 401
        - В токене нет scope - 401
        - В токене нет aud - 401
        - В токене нет iat - 401
        - Нет хедера x-telegram-user-id - 401
        - Неправильный sub - 401
        - Неправильный iss - 401
        - Неправильный aud - 401
        - Неправильный iat - 401
        - Неправильный scope - 401
        - Неправильный client_id - 401
        - Неправильный x_telegram_user_id - 401
        """
        token: str | None = None

        if invalid_case.token_fields is not None:
            token = jwt_token_factory(
                token_fields=invalid_case.token_fields,
            )

        response = auth_service_v0_api_client.update_resource(
            asdict(DEFAULT_UPDATE_RESOURCE_REQUEST),
            token=token,
            x_telegram_user_id=invalid_case.telegram_user_id,
        )
        assert response.status_code == invalid_case.expected_status_code, response.text

        if invalid_case.expected_message is not None:
            assert invalid_case.expected_message == response.json()[fields.ERROR_FIELD]

        log_internal_server_error(response, logger, fields.ERROR_FIELD)

        if invalid_case.expected_response is not None:
            resource.assert_api_response(response.json(), invalid_case.expected_response)

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        if message and expected_audit_message is not None:
            real_message = audit.AuditMessage.model_validate_json(message)
            audit.assert_audit_message(expected_audit_message, real_message)
            audit.assert_audit_message_context(expected_audit_message, real_message)
        elif expected_audit_message is not None:
            pytest.fail("No audit messages in queue")
