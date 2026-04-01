import logging, time  # noqa: E401
from collections.abc import Callable
from dataclasses import dataclass

import httpx, pytest  # noqa: E401 
from src.common.server_error_logging import log_internal_server_error
from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common.errors import INVALID_CLIENT_ERROR, INVALID_TOKEN_ERROR
from src.common.fields import (
    AUDIENCE_INTERNAL_API,
    CAN_EDIT_FIELD,
    CAN_READ_FIELD,
    ERROR_FIELD,
    ISSUER_AUTH_SERVICE,
    NOTE_IDS_FIELD,
    NOTES_FIELD,
    SCOPE_ADMIN,
)
from src.common.fields import (
    SCOPE_BOT,
    SPACE_ID_FIELD,
    SUBJECT_ADMIN,
    SUBJECT_BOT,
)
from src.common.ids import (
    ADMIN_USER_ID,
    big_list_without_existing_notes,
    BIG_LIST_WITH_EXISTING_PERSONAL_NOTES,
    BIG_LIST_WITH_EXISTING_SHARED_NOTES,
    EDITOR_USER_ID,
    ADMIN_NOTE,
    EDITOR_NOTE,
    OWNER_NOTE,
)
from src.common.ids import (
    PERSONAL_NOTES,
    PERSONAL_SPACE_ID,
    PERSONAL_SPACE_OWNER_USER_ID,
    RANDOM_INVALID_USER_ID,
    SHARED_SPACE_ID,
    SHARED_SPACE_OWNER_USER_ID,
    VIEWER_NOTE,
    VIEWER_USER_ID,
)
from tests.fixtures.auth_jwt import TokenFields

logger = logging.getLogger(__name__)

ONE_HOUR_SECONDS = 60 * 60


@dataclass(frozen=True)
class FilterNotesCase:
    """Ожидаемый сценарий для вызова filter_notes."""
    x_telegram_user_id: int | None # от кого запрос (telegram user id)
    body: dict | None
    expected_status_code: int
    expected_response: dict | None
    expected_message: str | None


@dataclass(frozen=True)
class InvalidFilterNotesTokenCase:
    """Сценарий негативной проверки токена для filter_notes."""
    token_fields: TokenFields | None
    expected_status_code: int
    telegram_user_id: int | None
    expected_message: str | None
    expected_response: dict | None


class TestAuthServiceV0Notes:
    """Тесты для проверки работы с заметками"""

    @pytest.mark.parametrize(
        "case",
        [
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: PERSONAL_NOTES, SPACE_ID_FIELD: None},
                    x_telegram_user_id=PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.BAD_REQUEST,
                    expected_response=None,
                    expected_message="empty space id",
                ),
                id="empty space id",
            ),
            pytest.param(
                FilterNotesCase(
                    body={SPACE_ID_FIELD: PERSONAL_SPACE_ID},
                    x_telegram_user_id=PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.BAD_REQUEST,
                    expected_response=None,
                    expected_message="empty note id list",
                ),
                id="note_ids is empty",
            ),
             pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: PERSONAL_NOTES, SPACE_ID_FIELD: PERSONAL_SPACE_ID},
                    x_telegram_user_id=EDITOR_USER_ID,
                    expected_status_code=httpx.codes.FORBIDDEN,
                    expected_response=None,
                    expected_message="user is not member",
                ),
                id="user is not member",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: PERSONAL_NOTES, SPACE_ID_FIELD: PERSONAL_SPACE_ID},
                    x_telegram_user_id=PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            PERSONAL_NOTES[0]: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            PERSONAL_NOTES[1]: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            PERSONAL_NOTES[2]: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="valid request: only real IDs (personal space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: [OWNER_NOTE, ADMIN_NOTE, EDITOR_NOTE, VIEWER_NOTE], SPACE_ID_FIELD: PERSONAL_SPACE_ID},
                    x_telegram_user_id=PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={NOTES_FIELD: {}},
                    expected_message=None,
                ),
                id="valid request: only not real IDs (personal space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: big_list_without_existing_notes, SPACE_ID_FIELD: PERSONAL_SPACE_ID},
                    x_telegram_user_id=PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={NOTES_FIELD: {}},
                    expected_message=None,
                ),
                id="valid request: generated 1000 IDs (without existing notes) (personal space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_PERSONAL_NOTES, SPACE_ID_FIELD: PERSONAL_SPACE_ID},
                    x_telegram_user_id=PERSONAL_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            PERSONAL_NOTES[0]: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            PERSONAL_NOTES[1]: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            PERSONAL_NOTES[2]: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="valid request: generated 1000 IDs (personal space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: [OWNER_NOTE, ADMIN_NOTE, EDITOR_NOTE, VIEWER_NOTE], SPACE_ID_FIELD: SHARED_SPACE_ID},
                    x_telegram_user_id=SHARED_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            OWNER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            ADMIN_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            EDITOR_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            VIEWER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="user=OWNER, notes=SPACE (only existing notes) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_SHARED_NOTES, SPACE_ID_FIELD: SHARED_SPACE_ID},
                    x_telegram_user_id=SHARED_SPACE_OWNER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            OWNER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            ADMIN_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            EDITOR_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            VIEWER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="user=OWNER, notes=SPACE (existing notes+not existing) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: [OWNER_NOTE, ADMIN_NOTE, EDITOR_NOTE, VIEWER_NOTE], SPACE_ID_FIELD: SHARED_SPACE_ID},
                    x_telegram_user_id=ADMIN_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            OWNER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            ADMIN_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            EDITOR_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            VIEWER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="user=ADMIN, notes=SPACE (only existing notes) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_SHARED_NOTES, SPACE_ID_FIELD: SHARED_SPACE_ID},
                    x_telegram_user_id=ADMIN_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            OWNER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            ADMIN_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            EDITOR_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            VIEWER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="user=ADMIN, notes=SPACE (existing notes+not existing) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: [OWNER_NOTE, ADMIN_NOTE, EDITOR_NOTE, VIEWER_NOTE], SPACE_ID_FIELD: SHARED_SPACE_ID},
                    x_telegram_user_id=EDITOR_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            OWNER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            ADMIN_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            EDITOR_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            VIEWER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="user=EDITOR, notes=SPACE (only existing notes) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_SHARED_NOTES, SPACE_ID_FIELD: SHARED_SPACE_ID},
                    x_telegram_user_id=EDITOR_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            OWNER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            ADMIN_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            EDITOR_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            VIEWER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="user=EDITOR, notes=SPACE (existing notes+not existing) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: [OWNER_NOTE, ADMIN_NOTE, EDITOR_NOTE, VIEWER_NOTE], SPACE_ID_FIELD: SHARED_SPACE_ID},
                    x_telegram_user_id=VIEWER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            OWNER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: False},
                            ADMIN_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: False},
                            EDITOR_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: False},
                            VIEWER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: False},
                        }
                    },
                    expected_message=None,
                ),
                id="user=VIEWER, notes=SPACE (only existing notes) (shared space)",
            ),
            pytest.param(
                FilterNotesCase(
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_SHARED_NOTES, SPACE_ID_FIELD: SHARED_SPACE_ID},
                    x_telegram_user_id=VIEWER_USER_ID,
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            OWNER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: False},
                            ADMIN_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: False},
                            EDITOR_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: False},
                            VIEWER_NOTE: {CAN_READ_FIELD: True, CAN_EDIT_FIELD: False},
                        }
                    },
                    expected_message=None,
                ),
                id="user=VIEWER, notes=SPACE (existing notes+not existing) (shared space)",
            ),
        ],
    )
    def test_filter_notes(
        self,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        login: str,
        case: FilterNotesCase,
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
        log_internal_server_error(response, logger, ERROR_FIELD)
        assert response.status_code == case.expected_status_code, response.text

        if case.expected_message is not None:
            assert case.expected_message == response.json()[ERROR_FIELD]

        if case.expected_response is not None:
            assert case.expected_response == response.json()

    @pytest.mark.parametrize(
        "invalid_case",
        [
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=[AUDIENCE_INTERNAL_API],
                        sub=SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) - ONE_HOUR_SECONDS,
                        scope=SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=(
                        INVALID_TOKEN_ERROR
                    ),
                    expected_response=None,
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
                id="no token",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=[AUDIENCE_INTERNAL_API],
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message="invalid token: invalid client id",
                    expected_response=None,
                ),
                id="token without sub",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        aud=[AUDIENCE_INTERNAL_API],
                        sub=SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=(
                        INVALID_TOKEN_ERROR
                    ),
                    expected_response=None,
                ),
                id="token without iss",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=[AUDIENCE_INTERNAL_API],
                        sub=SUBJECT_BOT,
                        iat=int(time.time()),
                        scope=SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=(
                        INVALID_TOKEN_ERROR
                    ),
                    expected_response=None,
                ),
                id="token without exp",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=[AUDIENCE_INTERNAL_API],
                        sub=SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message="invalid token: invalid scope",
                    expected_response=None,
                ),
                id="token without scope",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        sub=SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=(
                        INVALID_TOKEN_ERROR
                    ),
                    expected_response=None,
                ),
                id="token without aud",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=[AUDIENCE_INTERNAL_API],
                        sub=SUBJECT_BOT,
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=(
                        INVALID_TOKEN_ERROR
                    ),
                    expected_response=None,
                ),
                id="token without iat",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=[AUDIENCE_INTERNAL_API],
                        sub=SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=(
                        "invalid request: header 'X-Telegram-User-Id' not found"
                    ),
                    expected_response=None,
                ),
                id="no x-telegram-user-id",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=[AUDIENCE_INTERNAL_API],
                        sub=SUBJECT_ADMIN,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=INVALID_CLIENT_ERROR,
                    expected_response=None,
                ),
                id="invalid client",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss="zanuda-other-service",
                        aud=[AUDIENCE_INTERNAL_API],
                        sub=SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=(
                        INVALID_TOKEN_ERROR
                    ),
                    expected_response=None,
                ),
                id="invalid issuer",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=["zanuda-other-api"],
                        sub=SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=(
                        INVALID_TOKEN_ERROR
                    ),
                    expected_response=None,
                ),
                id="invalid aud",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=[AUDIENCE_INTERNAL_API],
                        sub=SUBJECT_BOT,
                        iat=int(time.time()) + ONE_HOUR_SECONDS,
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_BOT,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=(
                        INVALID_TOKEN_ERROR
                    ),
                    expected_response=None,
                ),
                id="invalid iat",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=[AUDIENCE_INTERNAL_API],
                        sub=SUBJECT_BOT,
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_ADMIN,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message="client does not have required scope",
                    expected_response=None,
                ),
                id="invalid scope",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=[AUDIENCE_INTERNAL_API],
                        sub="bot2",
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_ADMIN,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=None,
                    expected_message=INVALID_CLIENT_ERROR,
                    expected_response=None,
                ),
                id="invalid client id",
            ),
            pytest.param(
                InvalidFilterNotesTokenCase(
                    token_fields=TokenFields(
                        iss=ISSUER_AUTH_SERVICE,
                        aud=[AUDIENCE_INTERNAL_API],
                        sub="bot2",
                        iat=int(time.time()),
                        exp=int(time.time()) + ONE_HOUR_SECONDS,
                        scope=SCOPE_ADMIN,
                    ),
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    telegram_user_id=RANDOM_INVALID_USER_ID,
                    expected_message=INVALID_CLIENT_ERROR,
                    expected_response=None,
                ),
                id="invalid client id with telegram user",
            ),
        ],
    )
    def test_filter_notes_invalid_token(
        self,
        invalid_case: InvalidFilterNotesTokenCase,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        jwt_token_factory: Callable[..., str],
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
            assert invalid_case.expected_message == response.json()[ERROR_FIELD]

        log_internal_server_error(response, logger, ERROR_FIELD)

        if invalid_case.expected_response is not None:
            assert invalid_case.expected_response == response.json()
           
