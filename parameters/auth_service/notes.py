from parameters.auth_service import request_audit
import time
from dataclasses import dataclass
import httpx, pytest
import src.common.audit as audit
import src.common.fields as fields
import src.common.ids as ids
from tests.fixtures.auth_jwt import TokenFields

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


FILTER_NOTES_CASES = (
    pytest.param(
        FilterNotesCase(
            body={fields.NOTE_IDS_FIELD: ids.PERSONAL_NOTES, fields.SPACE_ID_FIELD: None},
            x_telegram_user_id=ids.PERSONAL_SPACE_OWNER_USER_ID,
            expected_status_code=httpx.codes.BAD_REQUEST,
            expected_response=None,
            expected_message="empty space id",
        ),
        request_audit.validation_failure(audit.Operation.POLITICS_FILTER_NOTES, "VALIDATION_FAILED", 'empty space id', level=audit.Level.DEBUG, stage="validate_request"),
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
        request_audit.validation_failure(audit.Operation.POLITICS_FILTER_NOTES, "VALIDATION_FAILED", 'empty note id list', level=audit.Level.DEBUG, stage="validate_request"),
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
                message="User is not a member of the space",
                context={
                    fields.NOTE_IDS_FIELD: [
                       *ids.PERSONAL_NOTES,# noqa: WPS356 # нужно распаковать, т.к. от сервера приходит список, а не tuple
                    ],
                    fields.SPACE_ID_FIELD: ids.PERSONAL_SPACE_ID,
                    fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT,
                    fields.USER_ID_FIELD: ids.EDITOR_USER_ID_UUID,
                    audit.STAGE_FIELD: "filter_notes",
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
)
"""Фильтрация заметок по UUID и правам пользователя в указанном пространстве.

- Вместо UUID пространства передан space_id=null: 400 Bad Request.
- В запросе отсутствует поле note_ids: 400 Bad Request.
- Редактор общего пространства запрашивает заметки в чужом личном пространстве: 403 Forbidden.
- Владелец личного пространства запрашивает свои заметки: 200 OK, доступны чтение и редактирование.
- Владелец указывает своё личное пространство, но передаёт UUID заметок из общего: 200 OK, объект notes пуст.
- Владелец личного пространства передаёт 1000 случайных UUID: 200 OK, объект notes пуст.
- К 1000 случайных UUID добавлены UUID личных заметок: 200 OK, возвращены только свои заметки с правом редактирования.
- Владелец общего пространства запрашивает заметки всех авторов: 200 OK, доступны чтение и редактирование.
- Тот же запрос от администратора: 200 OK, доступны чтение и редактирование.
- Тот же запрос от редактора: 200 OK, доступны чтение и редактирование.
- Тот же запрос от зрителя: 200 OK, для каждой возвращённой заметки разрешено только чтение.

Для каждой роли в общем пространстве проверяются два списка. В первом только существующие UUID.
Во втором к ним добавлены случайные UUID, и они должны отсутствовать в ответе.
"""


FILTER_NOTES_INVALID_TOKEN_CASES = (
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
            message=audit.TOKEN_VERIFICATION_FAILED,
            cause="token has invalid claims: token is expired",
            error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.POLITICS_FILTER_NOTES,
            status=audit.Status.FAILED,
            context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, audit.STAGE_FIELD: audit.AUTHENTICATE},
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
            message=audit.TOKEN_VERIFICATION_FAILED,
            error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
            cause="invalid token: no prefix Bearer",
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.POLITICS_FILTER_NOTES,
            status=audit.Status.FAILED,
            context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, audit.STAGE_FIELD: audit.AUTHENTICATE},
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
        request_audit.rejected_client(audit.Operation.POLITICS_FILTER_NOTES),
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
            message=audit.TOKEN_VERIFICATION_FAILED,
            cause="token has invalid claims: token is missing required claim: iss claim is required",
            error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.POLITICS_FILTER_NOTES,
            status=audit.Status.FAILED,
            context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, audit.STAGE_FIELD: audit.AUTHENTICATE},
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
            message=audit.TOKEN_VERIFICATION_FAILED,
            cause="token has invalid claims: token is missing required claim: exp claim is required",
            error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.POLITICS_FILTER_NOTES,
            status=audit.Status.FAILED,
            context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, audit.STAGE_FIELD: audit.AUTHENTICATE},
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
        request_audit.rejected_client(audit.Operation.POLITICS_FILTER_NOTES),
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
            message=audit.TOKEN_VERIFICATION_FAILED,
            cause="token has invalid claims: token is missing required claim: aud claim is required",
            error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.POLITICS_FILTER_NOTES,
            status=audit.Status.FAILED,
            context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, audit.STAGE_FIELD: audit.AUTHENTICATE},
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
            message=audit.TOKEN_VERIFICATION_FAILED,
            cause="token is missing required claim: iat claim is required",
            error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.POLITICS_FILTER_NOTES,
            status=audit.Status.FAILED,
            context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, audit.STAGE_FIELD: audit.AUTHENTICATE},
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
        request_audit.missing_telegram_header(audit.Operation.POLITICS_FILTER_NOTES),
        id="no x-telegram-user-id",
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
            expected_status_code=httpx.codes.BAD_REQUEST,
            telegram_user_id=ids.INVALID_USER_ID,
            expected_message="invalid Telegram user ID",
            expected_response=None,
        ),
        request_audit.malformed_telegram_header(audit.Operation.POLITICS_FILTER_NOTES),
        id="leading zeros in x-telegram-user-id",
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
        request_audit.rejected_client(audit.Operation.POLITICS_FILTER_NOTES),
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
            message=audit.TOKEN_VERIFICATION_FAILED,
            cause="token has invalid claims: token has invalid issuer",
            error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.POLITICS_FILTER_NOTES,
            status=audit.Status.FAILED,
            context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, audit.STAGE_FIELD: audit.AUTHENTICATE},
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
            message=audit.TOKEN_VERIFICATION_FAILED,
            cause="token has invalid claims: token has invalid audience",
            error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.POLITICS_FILTER_NOTES,
            status=audit.Status.FAILED,
            context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, audit.STAGE_FIELD: audit.AUTHENTICATE},
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
            message=audit.TOKEN_VERIFICATION_FAILED,
            cause="token has invalid claims: token used before issued",
            error_code=audit.ErrorCode.AUTH_TOKEN_INVALID,
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.POLITICS_FILTER_NOTES,
            status=audit.Status.FAILED,
            context={fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT, audit.STAGE_FIELD: audit.AUTHENTICATE},
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
        request_audit.rejected_client(audit.Operation.POLITICS_FILTER_NOTES),
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
        request_audit.rejected_client(audit.Operation.POLITICS_FILTER_NOTES),
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
        request_audit.rejected_client(audit.Operation.POLITICS_FILTER_NOTES),
        id="invalid client id with telegram user",
    ),
)
"""Отказ в доступе к notes/filter до фильтрации списка заметок.

- Telegram ID с ведущими нулями при действительном JWT: 400 Bad Request и аудит ошибки формата.

- Токен просрочен: 401 Unauthorized.
- Токен отсутствует: 401 Unauthorized.
- В JWT отсутствует sub (идентификатор клиента): 401 Unauthorized.
- В JWT отсутствует iss (издатель): 401 Unauthorized.
- В JWT отсутствует exp (срок действия): 401 Unauthorized.
- В JWT отсутствует scope (права клиента): 401 Unauthorized.
- В JWT отсутствует aud (получатель): 401 Unauthorized.
- В JWT отсутствует iat (время выдачи): 401 Unauthorized.
- Токен валиден, но отсутствует заголовок X-Telegram-User-Id: 401 Unauthorized.
- В sub передан клиент admin вместо bot: 401 Unauthorized.
- Указан другой издатель (iss): 401 Unauthorized.
- Указан другой получатель (aud): 401 Unauthorized.
- Время выдачи токена (iat) находится в будущем: 401 Unauthorized.
- Клиент bot передал scope admin: 401 Unauthorized.
- В sub передан неизвестный клиент bot2, заголовок X-Telegram-User-Id отсутствует: 401 Unauthorized.
- Тот же неизвестный клиент передал X-Telegram-User-Id: 401 Unauthorized, причина по-прежнему в клиенте.
"""
