import logging, time  
from collections.abc import Callable
from dataclasses import dataclass

import httpx, pytest  
from src.common.server_error_logging import log_internal_server_error
from src.api_clients.auth_service import AuthServiceV0APIClient
import src.common.audit as audit 

import src.common.fields as fields 

import src.common.ids as ids 
from tests.fixtures.auth_jwt import TokenFields
from typing import ContextManager, Optional

logger = logging.getLogger(__name__)

ONE_HOUR_SECONDS = 60 * 60


@dataclass(frozen=True)
class FilterNotesCase:
    """Ожидаемый сценарий для вызова filter_notes."""
    x_telegram_user_id: str | None # от кого запрос (telegram user id)
    body: dict | None
    expected_status_code: int
    expected_response: dict | None
    expected_message: str | None


@dataclass(frozen=True)
class InvalidFilterNotesTokenCase:
    """Сценарий негативной проверки токена для filter_notes."""
    token_fields: TokenFields | None
    expected_status_code: int
    telegram_user_id: str | None
    expected_message: str | None
    expected_response: dict | None


class TestAuthServiceV0Notes:
    """Тесты для проверки работы с заметками"""

    @pytest.mark.parametrize(
        ("case", "expected_audit_message"),
        [
            pytest.param(
                FilterNotesCase(
                    body={fields.NOTE_IDS_FIELD: ids.PERSONAL_NOTES, fields.SPACE_ID_FIELD: None},
                    x_telegram_user_id=ids.PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.BAD_REQUEST,
                    expected_response=None,
                    expected_message="empty space id",
                ),
                None,
                id="empty space id",
            ),
            pytest.param(
                FilterNotesCase(
                    body={fields.SPACE_ID_FIELD: ids.PERSONAL_SPACE_ID},
                    x_telegram_user_id=ids.PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.BAD_REQUEST,
                    expected_response=None,
                    expected_message="empty note id list",
                ),
                None,
                id="note_ids is empty",
            ),
             pytest.param(
                FilterNotesCase(
                    body={fields.NOTE_IDS_FIELD: ids.PERSONAL_NOTES, fields.SPACE_ID_FIELD: ids.PERSONAL_SPACE_ID},
                    x_telegram_user_id=ids.EDITOR_USER_ID,
                    expected_status_code=httpx.codes.FORBIDDEN,
                    expected_response=None,
                    expected_message="user is not member",
                ),
                 audit.AuditMessage(
                        service_name=audit.AUTH_SERVICE_NAME,
                        level=audit.Level.WARN,
                        error_code=audit.ErrorCode.PERM_DENIED_SPACE,
                        cause="user is not member",
                        kind=audit.Kind.DOMAIN,
                        operation=audit.Operation.POLITICS_FILTER_NOTES,
                        status=audit.Status.FAILED,
                        user_id=ids.EDITOR_USER_ID_UUID,
                        message=audit.Message.USER_IS_NOT_MEMBER,
                        context={
                            fields.NOTE_IDS_FIELD: [
                               *ids.PERSONAL_NOTES,# noqa: WPS356 # нужно распаковать, т.к. от сервера приходит список, а не tuple
                            ],
                            fields.SPACE_ID_FIELD: ids.PERSONAL_SPACE_ID,
                            fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT,
                            fields.USER_ID_FIELD: ids.EDITOR_USER_ID
                        },
                ),
                id="user is not member",
            ),
            pytest.param(
                FilterNotesCase(
                    body={fields.NOTE_IDS_FIELD: ids.PERSONAL_NOTES, fields.SPACE_ID_FIELD: ids.PERSONAL_SPACE_ID},
                    x_telegram_user_id=ids.PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        fields.NOTES_FIELD: {
                            ids.PERSONAL_NOTES[0]: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.PERSONAL_NOTES[1]: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.PERSONAL_NOTES[2]: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                None,
                id="valid request: only real IDs (personal space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={
                        fields.NOTE_IDS_FIELD: [ids.OWNER_NOTE, ids.ADMIN_NOTE, ids.EDITOR_NOTE, ids.VIEWER_NOTE],
                        fields.SPACE_ID_FIELD: ids.PERSONAL_SPACE_ID,
                    },
                    x_telegram_user_id=ids.PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={fields.NOTES_FIELD: {}},
                    expected_message=None,
                ),
                None,
                id="valid request: only not real IDs (personal space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={fields.NOTE_IDS_FIELD: ids.big_list_without_existing_notes, fields.SPACE_ID_FIELD: ids.PERSONAL_SPACE_ID},
                    x_telegram_user_id=ids.PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={fields.NOTES_FIELD: {}},
                    expected_message=None,
                ),
                None,
                id="valid request: generated 1000 IDs (without existing notes) (personal space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={fields.NOTE_IDS_FIELD: ids.BIG_LIST_WITH_EXISTING_PERSONAL_NOTES, fields.SPACE_ID_FIELD: ids.PERSONAL_SPACE_ID},
                    x_telegram_user_id=ids.PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        fields.NOTES_FIELD: {
                            ids.PERSONAL_NOTES[0]: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.PERSONAL_NOTES[1]: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.PERSONAL_NOTES[2]: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                None,
                id="valid request: generated 1000 IDs (personal space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={
                        fields.NOTE_IDS_FIELD: [ids.OWNER_NOTE, ids.ADMIN_NOTE, ids.EDITOR_NOTE, ids.VIEWER_NOTE],
                        fields.SPACE_ID_FIELD: ids.SHARED_SPACE_ID,
                    },
                    x_telegram_user_id=ids.SHARED_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        fields.NOTES_FIELD: {
                            ids.OWNER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.ADMIN_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.EDITOR_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.VIEWER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                None,
                id="user=OWNER, notes=SPACE (only existing notes) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={fields.NOTE_IDS_FIELD: ids.BIG_LIST_WITH_EXISTING_SHARED_NOTES, fields.SPACE_ID_FIELD: ids.SHARED_SPACE_ID},
                    x_telegram_user_id=ids.SHARED_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        fields.NOTES_FIELD: {
                            ids.OWNER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.ADMIN_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.EDITOR_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.VIEWER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                None,
                id="user=OWNER, notes=SPACE (existing notes+not existing) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={
                        fields.NOTE_IDS_FIELD: [ids.OWNER_NOTE, ids.ADMIN_NOTE, ids.EDITOR_NOTE, ids.VIEWER_NOTE],
                        fields.SPACE_ID_FIELD: ids.SHARED_SPACE_ID,
                    },
                    x_telegram_user_id=ids.ADMIN_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        fields.NOTES_FIELD: {
                            ids.OWNER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.ADMIN_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.EDITOR_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.VIEWER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                None,
                id="user=ADMIN, notes=SPACE (only existing notes) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={fields.NOTE_IDS_FIELD: ids.BIG_LIST_WITH_EXISTING_SHARED_NOTES, fields.SPACE_ID_FIELD: ids.SHARED_SPACE_ID},
                    x_telegram_user_id=ids.ADMIN_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        fields.NOTES_FIELD: {
                            ids.OWNER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.ADMIN_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.EDITOR_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.VIEWER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                None,
                id="user=ADMIN, notes=SPACE (existing notes+not existing) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={
                        fields.NOTE_IDS_FIELD: [ids.OWNER_NOTE, ids.ADMIN_NOTE, ids.EDITOR_NOTE, ids.VIEWER_NOTE],
                        fields.SPACE_ID_FIELD: ids.SHARED_SPACE_ID,
                    },
                    x_telegram_user_id=ids.EDITOR_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        fields.NOTES_FIELD: {
                            ids.OWNER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.ADMIN_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.EDITOR_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.VIEWER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                None,
                id="user=EDITOR, notes=SPACE (only existing notes) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={fields.NOTE_IDS_FIELD: ids.BIG_LIST_WITH_EXISTING_SHARED_NOTES, fields.SPACE_ID_FIELD: ids.SHARED_SPACE_ID},
                    x_telegram_user_id=ids.EDITOR_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        fields.NOTES_FIELD: {
                            ids.OWNER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.ADMIN_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.EDITOR_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                            ids.VIEWER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                None,
                id="user=EDITOR, notes=SPACE (existing notes+not existing) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={
                        fields.NOTE_IDS_FIELD: [ids.OWNER_NOTE, ids.ADMIN_NOTE, ids.EDITOR_NOTE, ids.VIEWER_NOTE],
                        fields.SPACE_ID_FIELD: ids.SHARED_SPACE_ID,
                    },
                    x_telegram_user_id=ids.VIEWER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        fields.NOTES_FIELD: {
                            ids.OWNER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: False},
                            ids.ADMIN_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: False},
                            ids.EDITOR_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: False},
                            ids.VIEWER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: False},
                        }
                    },
                    expected_message=None,
                ),
                None,
                id="user=VIEWER, notes=SPACE (only existing notes) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={fields.NOTE_IDS_FIELD: ids.BIG_LIST_WITH_EXISTING_SHARED_NOTES, fields.SPACE_ID_FIELD: ids.SHARED_SPACE_ID},
                    x_telegram_user_id=ids.VIEWER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        fields.NOTES_FIELD: {
                            ids.OWNER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: False},
                            ids.ADMIN_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: False},
                            ids.EDITOR_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: False},
                            ids.VIEWER_NOTE: {fields.CAN_READ_FIELD: True, fields.CAN_EDIT_FIELD: False},
                        }
                    },
                    expected_message=None,
                ),
                None,
                id="user=VIEWER, notes=SPACE (existing notes+not existing) (shared space)",
            ),
        ],
    )
    def test_filter_notes(
        self,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        login: str,
        case: FilterNotesCase,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
        expected_audit_message: audit.AuditMessage,
    ) -> None:
        """
        Тест на фильтрацию заметок.
        Все тесты проверяются с токеном, который получается у сервиса авторизации по ручке /api/v0/auth/login.
        - space_id пустой - 400
        - не указаны note_ids - 400
        - пользователь не участвует в пространстве - 403
        - валидный запрос с заметками которые существуют - 200 + список айди из запроса
        - валидный запрос с заметками которые существуют + которые не существуют - 200 + список которые существуют
        - валидный запрос только с заметками которых нет - 200 + пустой список
        - валидный запрос с большим количеством айди заметок (существуют + не существуют) - 200 + список из тех которые существуют
        - валидный запрос с большим количеством айди заметок (не существуют) - 200 + пустой список
        - пользователь - OWNER, получить все SPACE заметки (только существующие)
        - пользователь - OWNER, получить все SPACE заметки (существующие + рандомные)
        - пользователь - ADMIN, получить все SPACE заметки (только существующие)
        - пользователь - ADMIN, получить все SPACE заметки (существующие + рандомные)
        - пользователь - EDITOR, получить все SPACE заметки (только существующие)
        - пользователь - EDITOR, получить все SPACE заметки (существующие + рандомные)
        - пользователь - VIEWER, получить все SPACE заметки (только существующие)
        - пользователь - VIEWER, получить все SPACE заметки (существующие + рандомные)
        """
        token = login
        
        response = auth_service_v0_api_client.filter_notes(token=token, body=case.body, x_telegram_user_id=case.x_telegram_user_id)
        log_internal_server_error(response, logger, fields.ERROR_FIELD)
        assert response.status_code == case.expected_status_code, response.text

        if case.expected_message is not None:
            assert case.expected_message == response.json()[fields.ERROR_FIELD]

        if case.expected_response is not None:
            assert case.expected_response == response.json()

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
                    message = rabbitmq_message
        if message and expected_audit_message is not None:
            real_message = audit.AuditMessage.model_validate_json(message)
            
            audit.assert_audit_message(expected_audit_message, real_message)
            audit.assert_audit_message_context(expected_audit_message, real_message)
        elif expected_audit_message is not None:
            pytest.fail("Нет сообщений в очереди")

    @pytest.mark.parametrize(
        ("invalid_case", "expected_audit_message"),
        [
            pytest.param(
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
                InvalidFilterNotesTokenCase(
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
    def test_filter_notes_invalid_token(
        self,
        invalid_case: InvalidFilterNotesTokenCase,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        jwt_token_factory: Callable[..., str],
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """
        Тест на фильтрацию заметок.
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

        response = auth_service_v0_api_client.filter_notes(
            token=token,
            body=None,
            x_telegram_user_id=invalid_case.telegram_user_id,
        )
        assert response.status_code == invalid_case.expected_status_code, response.text

        if invalid_case.expected_message is not None:
            assert invalid_case.expected_message == response.json()[fields.ERROR_FIELD]

        log_internal_server_error(response, logger, fields.ERROR_FIELD)

        if invalid_case.expected_response is not None:
            assert invalid_case.expected_response == response.json()

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        if message and expected_audit_message is not None:
            real_message = audit.AuditMessage.model_validate_json(message)
            audit.assert_audit_message(expected_audit_message, real_message)
            audit.assert_audit_message_context(expected_audit_message, real_message)
        elif expected_audit_message is not None:
            pytest.fail("Нет сообщений в очереди")
