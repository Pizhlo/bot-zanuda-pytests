import logging, time  
from dataclasses import asdict, dataclass
from collections.abc import Callable
from typing import ContextManager, Optional
import httpx, pytest, uuid

from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common import audit, errors, fields, ids
from src.common.server_error_logging import log_internal_server_error
import src.models.resource as resource
from tests.fixtures.auth_jwt import TokenFields

logger = logging.getLogger(__name__)

NOTE_CREATED_REQUEST_ID = str(uuid.uuid4())
NOTE_OWNER_ID = ids.SHARED_SPACE_OWNER_UUID
NOTE_SPACE_ID = ids.SHARED_SPACE_ID
NOTE_ID = "1776f52a-8ce0-4bcd-9b75-0d3f2606883a"

NOTE_OWNER_SUBJECT = resource.format_ref(fields.ResourceType.USER, NOTE_OWNER_ID)
NOTE_RESOURCE = resource.format_ref(fields.ResourceType.NOTE, NOTE_ID)
NOTE_SPACE_SUBJECT = resource.format_ref(fields.ResourceType.SPACE, NOTE_SPACE_ID)

SPACE_OWNER_SUBJECT = resource.format_ref(fields.ResourceType.USER, ids.PERSONAL_SPACE_OWNER_UUID)
SPACE_RESOURCE = resource.format_ref(fields.ResourceType.SPACE, ids.PERSONAL_SPACE_ID)

ONE_HOUR_SECONDS = 60 * 60

SPACE_CREATED_REQUEST_ID = str(uuid.uuid4())

note_and_reminder_create_event_types = {
    fields.ResourceType.NOTE: fields.EventType.NOTE_CREATED,
    fields.ResourceType.REMINDER: fields.EventType.REMINDER_CREATED,
}

wrong_create_event_types = {
    fields.ResourceType.NOTE: fields.EventType.NOTE_UPDATED,
    fields.ResourceType.REMINDER: fields.EventType.REMINDER_UPDATED,
}


def _change_type_mismatch_message(allowed: tuple[str, ...], got: str) -> str:
    return (
        f"change type mismatch: expected one of `{', '.join(allowed)}`, got `{got}`"
    )


def _event_type_mismatch_message(expected: str, got: str) -> str:
    return f"event type mismatch: expected `{expected}`, got `{got}`"


def _make_create_request( # noqa: WPS211
    *,
    resource_type: str,
    resource_id: str,
    request_id: str,
    event_type: str,
    owner: resource.ResourceRef | None,
    parent: resource.ResourceRef | None,
    change_type: str = fields.ChangeType.RESOURCE_ADDED,
    operation: str = fields.Operation.CREATE,
) -> resource.ResourceChangeMessage:
    return resource.ResourceChangeMessage(
        request_id=request_id,
        resource=resource.ResourceRef(type=resource_type, id=resource_id),
        operation=operation,
        change_type=change_type,
        relations=resource.ResourceRelations(owner=owner, parent=parent),
        context=resource.ResourceEventContext(
            source_service=fields.NOTES_SERVICE_NAME,
            event_type=event_type,
        ),
    )


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


EMPTY_RESOURCE_REF = resource.ResourceRef(
    type="",
    id="00000000-0000-0000-0000-000000000000",
)

# DetailedError без текста: сервис оборачивает Err* в *fga.DetailedError
# с пустым message (Err с json:"-"), value часто null.
EMPTY_DETAILED_ERROR = resource.DetailedError()


@dataclass(frozen=True)
class ValidationErrorCase:
    """Сценарий негативной валидации тела update_resource."""

    request: resource.ResourceChangeMessage
    expected_response: resource.ResourceChangeErrorResponse
    expected_status_code: int = httpx.codes.BAD_REQUEST


def _validation_error_response(
    request: resource.ResourceChangeMessage,
    *,
    code: str,
    message: str,
    detailed_error: resource.DetailedError | None = None,
) -> resource.ResourceChangeErrorResponse:
    return resource.ResourceChangeErrorResponse(
        request_id=request.request_id,
        status=fields.Status.ERROR,
        operation_result=fields.OperationResult.FAILED,
        resource=request.resource,
        error=resource.ResourceChangeError(
            code=code,
            message=message,
            details=resource.ResourceChangeErrorDetails(
                operation=request.operation,
                detailed_error=detailed_error,
            ),
        ),
        meta=resource.ResourceChangeMeta(),
    )


def _validation_case(
    request: resource.ResourceChangeMessage,
    *,
    code: str,
    message: str,
    detailed_error: resource.DetailedError | None = None,
) -> ValidationErrorCase:
    return ValidationErrorCase(
        request=request,
        expected_response=_validation_error_response(
            request,
            code=code,
            message=message,
            detailed_error=detailed_error,
        ),
    )


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
                            details=resource.ResourceChangeErrorDetails(
                                operation=fields.Operation.CREATE,
                                detailed_error=EMPTY_DETAILED_ERROR,
                            ),
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
                            message=audit.Message.USER_NOT_FOUND,
                            details=resource.ResourceChangeErrorDetails(
                                operation=fields.Operation.CREATE,
                                detailed_error=EMPTY_DETAILED_ERROR,
                            ),
                        ),
                        meta=resource.ResourceChangeMeta(),
                    ),
                    expected_message=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.ERROR,
                    cause=audit.Message.NOT_FOUND,
                    error_code=audit.ErrorCode.USER_NOT_FOUND,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.FGA_UPDATE_RESOURCE,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, fields.USER_ID_FIELD: ids.INVALID_USER_ID},
                ),
                id="user not found",
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
        """
        token = login

        response = auth_service_v0_api_client.update_resource(asdict(case.request), token=token, x_telegram_user_id=case.x_telegram_user_id)
        log_internal_server_error(response, logger, fields.ERROR_FIELD)

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        assert response.status_code == case.expected_status_code, response.text

        if case.expected_message is not None:
            assert response.json()[fields.ERROR_FIELD] == case.expected_message

        if case.expected_response is not None:
            resource.assert_api_response(response.json(), case.expected_response)

        if message and expected_audit_message is not None:
            real_message = audit.AuditMessage.model_validate_json(message)
            audit.assert_audit_message(expected_audit_message, real_message)
            audit.assert_audit_message_context(expected_audit_message, real_message)
        elif expected_audit_message is not None:
            pytest.fail(errors.NO_AUDIT_MESSAGES_ERROR)

    @pytest.mark.parametrize(
        ("case", "expected_audit_message"),
        [
            pytest.param(
                UpdateResourceCase(
                    x_telegram_user_id=ids.ADMIN_USER_ID,
                    request=resource.ResourceChangeMessage(
                        request_id=SPACE_CREATED_REQUEST_ID,
                        resource=resource.ResourceRef(type=fields.ResourceType.SPACE, id=ids.PERSONAL_SPACE_ID),
                        operation=fields.Operation.CREATE,
                        change_type=fields.ChangeType.RESOURCE_ADDED,
                        relations=resource.ResourceRelations(
                            owner=resource.ResourceRef(type=fields.ResourceType.USER, id=ids.PERSONAL_SPACE_OWNER_UUID),
                            parent=None,
                        ),
                        context=resource.ResourceEventContext(
                            source_service=fields.NOTES_SERVICE_NAME,
                            event_type=fields.EventType.SPACE_CREATED,
                        ),
                    ),
                    expected_status_code=httpx.codes.OK,
                    expected_response=resource.ResourceChangeResponse(
                        request_id=SPACE_CREATED_REQUEST_ID,
                        idempotency_key="",
                        status=fields.Status.COMPLETED,
                        operation_result=fields.OperationResult.APPLIED,
                        resource=resource.ResourceRef(type=fields.ResourceType.SPACE, id=ids.PERSONAL_SPACE_ID),
                        written_tuples=(
                            resource.AuthTuple(
                                subject=SPACE_OWNER_SUBJECT,
                                relation=fields.Relation.OWNER,
                                resource=SPACE_RESOURCE,
                            ),
                        ),
                        deleted_tuples=(),
                        meta=resource.ResourceChangeMeta(),
                    ),
                    expected_message=None,
                ),
                None, # для успешных кейсов нет аудит сообщений
                id="space created",
            ),
             pytest.param(
                UpdateResourceCase(
                    x_telegram_user_id=ids.ADMIN_USER_ID,
                    request=resource.ResourceChangeMessage(
                        request_id=SPACE_CREATED_REQUEST_ID,
                        resource=resource.ResourceRef(type=fields.ResourceType.SPACE, id=ids.PERSONAL_SPACE_ID),
                        operation=fields.Operation.CREATE,
                        change_type=fields.ChangeType.RESOURCE_ADDED,
                        relations=resource.ResourceRelations(
                            owner=resource.ResourceRef(type=fields.ResourceType.USER, id=ids.PERSONAL_SPACE_OWNER_UUID),
                            parent=None,
                        ),
                        context=resource.ResourceEventContext(
                            source_service=fields.NOTES_SERVICE_NAME,
                            event_type=fields.EventType.SPACE_CREATED,
                        ),
                    ),
                    expected_status_code=httpx.codes.CONFLICT,
                    expected_response=resource.ResourceChangeErrorResponse(
                        request_id=SPACE_CREATED_REQUEST_ID,
                        status=fields.Status.ERROR,
                        operation_result=fields.OperationResult.FAILED,
                        resource=resource.ResourceRef(type=fields.ResourceType.SPACE, id=ids.PERSONAL_SPACE_ID),
                        error=resource.ResourceChangeError(
                            code=audit.ErrorCode.RESOURCE_ALREADY_EXISTS_OR_NOT_FOUND,
                            message="new resource already exists or deleted resource not found",
                            details=resource.ResourceChangeErrorDetails(
                                operation=fields.Operation.CREATE,
                                detailed_error=EMPTY_DETAILED_ERROR,
                            ),
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
                        f'"message":"cannot write a tuple which already exists: user: \'user:{ids.PERSONAL_SPACE_OWNER_UUID}\', relation: \'owner\', object: \'space:{ids.PERSONAL_SPACE_ID}\': tuple to be written already existed or the tuple to be deleted did not exist"}}\n'
                        f" with error code write_failed_due_to_invalid_input error message: cannot write a tuple which already exists: user: 'user:{ids.PERSONAL_SPACE_OWNER_UUID}', relation: 'owner', object: 'space:{ids.PERSONAL_SPACE_ID}': tuple to be written already existed or the tuple to be deleted did not exist"
                    ),
                    error_code=audit.ErrorCode.WRITE_FAILED_DUE_TO_INVALID_INPUT,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.FGA_UPDATE_RESOURCE,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, fields.USER_ID_FIELD: ids.ADMIN_USER_ID},
                ),
                id="space already exists",
            ),
             pytest.param(
                UpdateResourceCase(
                    x_telegram_user_id=ids.INVALID_USER_ID,
                    request=resource.ResourceChangeMessage(
                        request_id=SPACE_CREATED_REQUEST_ID,
                        resource=resource.ResourceRef(type=fields.ResourceType.SPACE, id=ids.PERSONAL_SPACE_ID),
                        operation=fields.Operation.CREATE,
                        change_type=fields.ChangeType.RESOURCE_ADDED,
                        relations=resource.ResourceRelations(
                            owner=resource.ResourceRef(type=fields.ResourceType.USER, id=ids.PERSONAL_SPACE_OWNER_UUID),
                            parent=None,
                        ),
                        context=resource.ResourceEventContext(
                            source_service=fields.NOTES_SERVICE_NAME,
                            event_type=fields.EventType.SPACE_CREATED,
                        ),
                    ),
                    expected_status_code=httpx.codes.NOT_FOUND,
                    expected_response=resource.ResourceChangeErrorResponse(
                        request_id=SPACE_CREATED_REQUEST_ID,
                        status=fields.Status.ERROR,
                        operation_result=fields.OperationResult.FAILED,
                        resource=resource.ResourceRef(type=fields.ResourceType.SPACE, id=ids.PERSONAL_SPACE_ID),
                        error=resource.ResourceChangeError(
                            code=audit.ErrorCode.USER_NOT_FOUND,
                            message=audit.Message.USER_NOT_FOUND,
                            details=resource.ResourceChangeErrorDetails(
                                operation=fields.Operation.CREATE,
                                detailed_error=EMPTY_DETAILED_ERROR,
                            ),
                        ),
                        meta=resource.ResourceChangeMeta(),
                    ),
                    expected_message=None,
                ),
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.ERROR,
                    cause=audit.Message.NOT_FOUND,
                    error_code=audit.ErrorCode.USER_NOT_FOUND,
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.FGA_UPDATE_RESOURCE,
                    status=audit.Status.FAILED,
                    context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, fields.USER_ID_FIELD: ids.INVALID_USER_ID},
                ),
                id="user not found",
            ),
        ],
    )
    def test_create_space(     
        self,
        case: UpdateResourceCase,
        login: str,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],) -> None:
        """
        Тест на создание пространства.
        - Успешное создание пространства: 200 OK
        - Пространство уже существует: 409 Conflict
        - Пользователя не существует (хедер x-telegram-user-id): 404 Not Found
        """
        token = login

        response = auth_service_v0_api_client.update_resource(asdict(case.request), token=token, x_telegram_user_id=case.x_telegram_user_id)
        log_internal_server_error(response, logger, fields.ERROR_FIELD)

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        assert response.status_code == case.expected_status_code, response.text

        if case.expected_message is not None:
            assert response.json()[fields.ERROR_FIELD] == case.expected_message

        if case.expected_response is not None:
            resource.assert_api_response(response.json(), case.expected_response)

        if message and expected_audit_message is not None:
            real_message = audit.AuditMessage.model_validate_json(message)
            audit.assert_audit_message(expected_audit_message, real_message)
            audit.assert_audit_message_context(expected_audit_message, real_message)
        elif expected_audit_message is not None:
            pytest.fail(errors.NO_AUDIT_MESSAGES_ERROR)

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
        log_internal_server_error(response, logger, fields.ERROR_FIELD)

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        assert response.status_code == invalid_case.expected_status_code, response.text

        if invalid_case.expected_message is not None:
            assert invalid_case.expected_message == response.json()[fields.ERROR_FIELD]

        if invalid_case.expected_response is not None:
            resource.assert_api_response(response.json(), invalid_case.expected_response)

        if message and expected_audit_message is not None:
            real_message = audit.AuditMessage.model_validate_json(message)
            audit.assert_audit_message(expected_audit_message, real_message)
            audit.assert_audit_message_context(expected_audit_message, real_message)
        elif expected_audit_message is not None:
            pytest.fail(errors.NO_AUDIT_MESSAGES_ERROR)

    @pytest.mark.parametrize(
        "case",
        [
            *[
                pytest.param(
                    _validation_case(
                        _make_create_request(
                            resource_type=resource_type,
                            resource_id=str(uuid.uuid4()),
                            request_id=str(uuid.uuid4()),
                            event_type=event_type,
                            owner=None,
                            parent=resource.ResourceRef(
                                type=fields.ResourceType.SPACE, id=NOTE_SPACE_ID
                            ),
                        ),
                        code=audit.ErrorCode.OWNER_REQUIRED,
                        message=audit.Message.OWNER_REQUIRED,
                        detailed_error=resource.DetailedError(value=EMPTY_RESOURCE_REF),
                    ),
                    id=f"{resource_type}: owner required",
                )
                for resource_type, event_type in note_and_reminder_create_event_types.items()
            ],
            *[
                pytest.param(
                    _validation_case(
                        _make_create_request(
                            resource_type=resource_type,
                            resource_id=str(uuid.uuid4()),
                            request_id=str(uuid.uuid4()),
                            event_type=event_type,
                            owner=resource.ResourceRef(
                                type=fields.ResourceType.SPACE, id=NOTE_OWNER_ID
                            ),
                            parent=resource.ResourceRef(
                                type=fields.ResourceType.SPACE, id=NOTE_SPACE_ID
                            ),
                        ),
                        code=audit.ErrorCode.OWNER_TYPE_INVALID,
                        message=audit.Message.OWNER_TYPE_INVALID,
                        detailed_error=resource.DetailedError(
                            value=resource.ResourceRef(
                                type=fields.ResourceType.SPACE, id=NOTE_OWNER_ID
                            ),
                        ),
                    ),
                    id=f"{resource_type}: owner type invalid",
                )
                for resource_type, event_type in note_and_reminder_create_event_types.items()
            ],
            *[
                pytest.param(
                    _validation_case(
                        _make_create_request(
                            resource_type=resource_type,
                            resource_id=str(uuid.uuid4()),
                            request_id=str(uuid.uuid4()),
                            event_type=event_type,
                            owner=resource.ResourceRef(
                                type=fields.ResourceType.USER, id=NOTE_OWNER_ID
                            ),
                            parent=None,
                        ),
                        code=audit.ErrorCode.PARENT_REQUIRED,
                        message=audit.Message.PARENT_REQUIRED,
                        detailed_error=resource.DetailedError(value=EMPTY_RESOURCE_REF),
                    ),
                    id=f"{resource_type}: parent required",
                )
                for resource_type, event_type in note_and_reminder_create_event_types.items()
            ],
            *[
                pytest.param(
                    _validation_case(
                        _make_create_request(
                            resource_type=resource_type,
                            resource_id=str(uuid.uuid4()),
                            request_id=str(uuid.uuid4()),
                            event_type=event_type,
                            owner=resource.ResourceRef(
                                type=fields.ResourceType.USER, id=NOTE_OWNER_ID
                            ),
                            parent=resource.ResourceRef(
                                type=fields.ResourceType.USER, id=NOTE_SPACE_ID
                            ),
                        ),
                        code=audit.ErrorCode.PARENT_TYPE_INVALID,
                        message=audit.Message.PARENT_TYPE_INVALID,
                        detailed_error=resource.DetailedError(
                            value=resource.ResourceRef(
                                type=fields.ResourceType.USER, id=NOTE_SPACE_ID
                            ),
                        ),
                    ),
                    id=f"{resource_type}: parent type invalid",
                )
                for resource_type, event_type in note_and_reminder_create_event_types.items()
            ],
            *[
                pytest.param(
                    _validation_case(
                        _make_create_request(
                            resource_type=resource_type,
                            resource_id=str(uuid.uuid4()),
                            request_id=str(uuid.uuid4()),
                            event_type=event_type,
                            owner=resource.ResourceRef(
                                type=fields.ResourceType.USER, id=NOTE_OWNER_ID
                            ),
                            parent=resource.ResourceRef(
                                type=fields.ResourceType.SPACE, id=NOTE_SPACE_ID
                            ),
                            change_type=fields.ChangeType.MEMBERSHIP_CHANGED,
                            operation=fields.Operation.UPDATE,
                        ),
                        code=audit.ErrorCode.CHANGE_TYPE_INVALID,
                        message=audit.Message.CHANGE_TYPE_INVALID,
                        detailed_error=resource.DetailedError(
                            message=_change_type_mismatch_message(
                                fields.NOTE_AND_REMINDER_CHANGE_TYPES,
                                fields.ChangeType.MEMBERSHIP_CHANGED,
                            ),
                            value=fields.ChangeType.MEMBERSHIP_CHANGED,
                        ),
                    ),
                    id=f"{resource_type}: change type not allowed",
                )
                for resource_type, event_type in note_and_reminder_create_event_types.items()
            ],
            *[
                pytest.param(
                    _validation_case(
                        _make_create_request(
                            resource_type=resource_type,
                            resource_id=str(uuid.uuid4()),
                            request_id=str(uuid.uuid4()),
                            event_type=wrong_event_type,
                            owner=resource.ResourceRef(
                                type=fields.ResourceType.USER, id=NOTE_OWNER_ID
                            ),
                            parent=resource.ResourceRef(
                                type=fields.ResourceType.SPACE, id=NOTE_SPACE_ID
                            ),
                        ),
                        code=audit.ErrorCode.EVENT_TYPE_INVALID,
                        message=audit.Message.EVENT_TYPE_INVALID,
                        detailed_error=resource.DetailedError(
                            message=_event_type_mismatch_message(
                                expected_event_type, wrong_event_type
                            ),
                            value=wrong_event_type,
                        ),
                    ),
                    id=f"{resource_type}: event type mismatch",
                )
                for resource_type, expected_event_type in note_and_reminder_create_event_types.items()
                for wrong_event_type in (wrong_create_event_types[resource_type],)
            ],
            pytest.param(
                _validation_case(
                    _make_create_request(
                        resource_type=fields.ResourceType.SPACE,
                        resource_id=str(uuid.uuid4()),
                        request_id=str(uuid.uuid4()),
                        event_type=fields.EventType.SPACE_CREATED,
                        owner=None,
                        parent=None,
                    ),
                    code=audit.ErrorCode.OWNER_REQUIRED,
                    message=audit.Message.OWNER_REQUIRED,
                    detailed_error=resource.DetailedError(value=EMPTY_RESOURCE_REF),
                ),
                id="space: owner required",
            ),
            pytest.param(
                _validation_case(
                    _make_create_request(
                        resource_type=fields.ResourceType.SPACE,
                        resource_id=str(uuid.uuid4()),
                        request_id=str(uuid.uuid4()),
                        event_type=fields.EventType.SPACE_CREATED,
                        owner=resource.ResourceRef(
                            type=fields.ResourceType.USER,
                            id=ids.PERSONAL_SPACE_OWNER_UUID,
                        ),
                        parent=resource.ResourceRef(
                            type=fields.ResourceType.SPACE, id=NOTE_SPACE_ID
                        ),
                    ),
                    code=audit.ErrorCode.PARENT_NOT_ALLOWED,
                    message=audit.Message.PARENT_NOT_ALLOWED,
                    detailed_error=resource.DetailedError(
                        message="spaces do not have parents, only owners",
                        value=resource.ResourceRef(
                            type=fields.ResourceType.SPACE, id=NOTE_SPACE_ID
                        ),
                    ),
                ),
                id="space: parent not allowed",
            ),
            pytest.param(
                _validation_case(
                    _make_create_request(
                        resource_type=fields.ResourceType.SPACE,
                        resource_id=str(uuid.uuid4()),
                        request_id=str(uuid.uuid4()),
                        event_type=fields.EventType.SPACE_CREATED,
                        owner=resource.ResourceRef(
                            type=fields.ResourceType.USER,
                            id=ids.PERSONAL_SPACE_OWNER_UUID,
                        ),
                        parent=None,
                        change_type=fields.ChangeType.RESOURCE_MOVED,
                        operation=fields.Operation.UPDATE,
                    ),
                    code=audit.ErrorCode.CHANGE_TYPE_INVALID,
                    message=audit.Message.CHANGE_TYPE_INVALID,
                    detailed_error=resource.DetailedError(
                        message=_change_type_mismatch_message(
                            fields.SPACE_CHANGE_TYPES,
                            fields.ChangeType.RESOURCE_MOVED,
                        ),
                        value=fields.ChangeType.RESOURCE_MOVED,
                    ),
                ),
                id="space: change type not allowed",
            ),
            pytest.param(
                _validation_case(
                    _make_create_request(
                        resource_type=fields.ResourceType.SPACE,
                        resource_id=str(uuid.uuid4()),
                        request_id=str(uuid.uuid4()),
                        event_type=fields.EventType.SPACE_UPDATED,
                        owner=resource.ResourceRef(
                            type=fields.ResourceType.USER,
                            id=ids.PERSONAL_SPACE_OWNER_UUID,
                        ),
                        parent=None,
                    ),
                    code=audit.ErrorCode.EVENT_TYPE_INVALID,
                    message=audit.Message.EVENT_TYPE_INVALID,
                    detailed_error=resource.DetailedError(
                        message=_event_type_mismatch_message(
                            fields.EventType.SPACE_CREATED,
                            fields.EventType.SPACE_UPDATED,
                        ),
                        value=fields.EventType.SPACE_UPDATED,
                    ),
                ),
                id="space: event type mismatch",
            ),
        ],
    )
    def test_update_resource_validation_errors(
        self,
        case: ValidationErrorCase,
        login: str,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """
        Тест на валидацию запросов update_resource при создании ресурсов.

        Заметки и напоминания:
        - обязательны relations.owner (type=user) и relations.parent (type=space)
        - change_type только из NOTE_AND_REMINDER_CHANGE_TYPES
        - event_type должен соответствовать операции (для create — *_CREATED)

        Пространства:
        - обязателен owner, parent запрещён
        - change_type только из SPACE_CHANGE_TYPES
        - event_type должен соответствовать операции
        """
        response = auth_service_v0_api_client.update_resource(
            asdict(case.request),
            token=login,
            x_telegram_user_id=ids.ADMIN_USER_ID,
        )
        log_internal_server_error(response, logger, fields.ERROR_FIELD)

        # validateRequest в fga.UpdateResource: level=debug,
        # error_code=WRITE_FAILED_DUE_TO_INVALID_INPUT, cause=Err.Error()
        # (совпадает с error.message в HTTP-ответе).
        validation_audit_message = audit.AuditMessage(
            service_name=audit.AUTH_SERVICE_NAME,
            level=audit.Level.DEBUG,
            cause=case.expected_response.error.message,
            error_code=audit.ErrorCode.WRITE_FAILED_DUE_TO_INVALID_INPUT,
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.FGA_UPDATE_RESOURCE,
            status=audit.Status.FAILED,
            context={
                fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT,
                fields.USER_ID_FIELD: ids.ADMIN_USER_ID,
            },
        )

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        if message:
            real_message = audit.AuditMessage.model_validate_json(message)
            audit.assert_audit_message(validation_audit_message, real_message)
            audit.assert_audit_message_context(validation_audit_message, real_message)
        else:
            pytest.fail(errors.NO_AUDIT_MESSAGES_ERROR)

        assert response.status_code == case.expected_status_code, response.text
        resource.assert_api_response(response.json(), case.expected_response)
