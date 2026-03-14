import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import uuid

import httpx
import pytest

from src.api_clients.auth_service import AuthServiceV0APIClient

# FIELDS
ERROR_FIELD = "error"
NOTE_IDS_FIELD = "note_ids"
SPACE_ID_FIELD = "space_id"
NOTES_FIELD = "notes"
CAN_READ_FIELD = "can_read"
CAN_EDIT_FIELD = "can_edit"

ONE_HOUR_SECONDS = int(timedelta(hours=1).total_seconds())

# детерминированный пользователь, которого нет в базе фикстур
NON_MEMBER_USER_ID = "2b5d2b63-8144-4cb7-b9c9-9e3c1cbac060"

# USERS
PERSONAL_SPACE_OWNER="56279a7c-13a0-4464-98fe-8cee52bcd3b7"
SHARED_SPACE_OWNER="56279a7c-13a0-4464-98fe-8cee52bcd3b7"
ADMIN_USER_ID="d1b3a949-8565-4268-8c72-6d27247cbaa5"
EDITOR_USER_ID="33fd6e4c-26d3-45a6-93e2-3a0514cfac5a"
VIEWER_USER_ID="0e9c136b-eee9-4d2b-bba3-fc32a9b5f2b4"

# SPACES
SHARED_SPACE_ID="7cc54caa-1753-4839-aa0c-6f2a76a08e93"
PERSONAL_SPACE_ID="c7adddae-4949-49e6-b57e-1aa4e8be7fdb"

# PRIVATE NOTES
PERSONAL_NOTES = (
    "697724a2-3333-457d-abef-01dffd94db08",
    "5aadeae9-c8ef-4146-bf41-f3128afa0c9f",
    "a34bd9cd-6f8d-48ff-81e6-9a49a3aba2e5",
)

# SHARED NOTES
OWNER_NOTE="1776f52a-8ce0-4bcd-9b75-0d3f2606883a"
ADMIN_NOTE="c50fddd1-fa97-4019-abcb-ad0a14d3cee7"
EDITOR_NOTE="269a5ff9-ae0b-463c-860b-0d87b9fead16"
VIEWER_NOTE="18bfb5da-3f5f-43b5-8b07-ef85887aec89"

SHARED_NOTES = (OWNER_NOTE, ADMIN_NOTE, EDITOR_NOTE, VIEWER_NOTE)

# ID LISTS
RANDOM_NOTES_COUNT = 1000
big_list_without_existing_notes = [str(uuid.uuid4()) for _ in range(RANDOM_NOTES_COUNT)]
BIG_LIST_WITHOUT_EXISTING_NOTES = tuple(str(uuid.uuid4()) for _ in range(1000))
BIG_LIST_WITH_EXISTING_PERSONAL_NOTES = (
    *BIG_LIST_WITHOUT_EXISTING_NOTES,
    *PERSONAL_NOTES,
)
BIG_LIST_WITH_EXISTING_SHARED_NOTES = (
    *BIG_LIST_WITHOUT_EXISTING_NOTES,
    *SHARED_NOTES,
)


@dataclass(frozen=True)
class TokenFields:
    """Параметры, из которых собирается payload токена."""
    user_id: str | None = None
    exp_offset: int | None = None


@dataclass(frozen=True)
class FilterNotesCase:
    """Ожидаемый сценарий для вызова filter_notes."""
    token_fields: TokenFields | None
    body: dict | None
    expected_status_code: int
    expected_response: dict | None
    expected_message: str | None


class TestAuthServiceV0Notes:
    """Тесты для проверки работы с заметками"""

    @pytest.mark.parametrize(
        "case",
        [
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=PERSONAL_SPACE_OWNER, exp_offset=-ONE_HOUR_SECONDS),
                    body=None,
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    expected_response=None,
                    expected_message="invalid token: token has invalid claims: token is expired",
                ),
                id="expired token",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=None,
                    body=None,
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    expected_response=None,
                    expected_message="invalid token: no prefix Bearer",
                ),
                id="no token",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(exp_offset=ONE_HOUR_SECONDS),
                    body=None,
                    expected_status_code=httpx.codes.UNAUTHORIZED,
                    expected_response=None,
                    expected_message="invalid token: field 'user_id' not found",
                ),
                id="token without user_id",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=PERSONAL_SPACE_OWNER, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: PERSONAL_NOTES, SPACE_ID_FIELD: None},
                    expected_status_code=httpx.codes.BAD_REQUEST,
                    expected_response=None,
                    expected_message="empty space id",
                ),
                id="empty space id",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=PERSONAL_SPACE_OWNER, exp_offset=ONE_HOUR_SECONDS),
                    body={SPACE_ID_FIELD: PERSONAL_SPACE_ID},
                    expected_status_code=httpx.codes.BAD_REQUEST,
                    expected_response=None,
                    expected_message="empty note id list",
                ),
                id="note_ids is empty",
            ),
             pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=NON_MEMBER_USER_ID, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: PERSONAL_NOTES, SPACE_ID_FIELD: PERSONAL_SPACE_ID},
                    expected_status_code=httpx.codes.FORBIDDEN,
                    expected_response=None,
                    expected_message="user is not member",
                ),
                id="user is not member",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=PERSONAL_SPACE_OWNER, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: PERSONAL_NOTES, SPACE_ID_FIELD: PERSONAL_SPACE_ID},
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
                    token_fields=TokenFields(user_id=PERSONAL_SPACE_OWNER, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: [OWNER_NOTE, ADMIN_NOTE, EDITOR_NOTE, VIEWER_NOTE], SPACE_ID_FIELD: PERSONAL_SPACE_ID},
                    expected_status_code=httpx.codes.OK,
                    expected_response={NOTES_FIELD: {}},
                    expected_message=None,
                ),
                id="valid request: only not real IDs (personal space)",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=PERSONAL_SPACE_OWNER, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: big_list_without_existing_notes, SPACE_ID_FIELD: PERSONAL_SPACE_ID},
                    expected_status_code=httpx.codes.OK,
                    expected_response={NOTES_FIELD: {}},
                    expected_message=None,
                ),
                id="valid request: generated 1000 IDs (without existing notes) (personal space)",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=PERSONAL_SPACE_OWNER, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_PERSONAL_NOTES, SPACE_ID_FIELD: PERSONAL_SPACE_ID},
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
                    token_fields=TokenFields(user_id=SHARED_SPACE_OWNER, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: [OWNER_NOTE, ADMIN_NOTE, EDITOR_NOTE, VIEWER_NOTE], SPACE_ID_FIELD: SHARED_SPACE_ID},
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
                    token_fields=TokenFields(user_id=SHARED_SPACE_OWNER, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_SHARED_NOTES, SPACE_ID_FIELD: SHARED_SPACE_ID},
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
                    token_fields=TokenFields(user_id=ADMIN_USER_ID, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: [OWNER_NOTE, ADMIN_NOTE, EDITOR_NOTE, VIEWER_NOTE], SPACE_ID_FIELD: SHARED_SPACE_ID},
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
                    token_fields=TokenFields(user_id=ADMIN_USER_ID, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_SHARED_NOTES, SPACE_ID_FIELD: SHARED_SPACE_ID},
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
                    token_fields=TokenFields(user_id=EDITOR_USER_ID, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: [OWNER_NOTE, ADMIN_NOTE, EDITOR_NOTE, VIEWER_NOTE], SPACE_ID_FIELD: SHARED_SPACE_ID},
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
                    token_fields=TokenFields(user_id=EDITOR_USER_ID, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_SHARED_NOTES, SPACE_ID_FIELD: SHARED_SPACE_ID},
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
                    token_fields=TokenFields(user_id=VIEWER_USER_ID, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: [OWNER_NOTE, ADMIN_NOTE, EDITOR_NOTE, VIEWER_NOTE], SPACE_ID_FIELD: SHARED_SPACE_ID},
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
                    token_fields=TokenFields(user_id=VIEWER_USER_ID, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_SHARED_NOTES, SPACE_ID_FIELD: SHARED_SPACE_ID},
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
        jwt_token_factory: Callable[..., str],
        case: FilterNotesCase,
    ) -> None:
        """
        Тест на фильтрацию заметок.
        - Протухший токен - 401
        - Токена нет - 401
        - В токене нет user_id - 401
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
        token: str | None = None
        token_fields = case.token_fields
        if token_fields is not None:
            exp: int | None = None
            if token_fields.exp_offset is not None:
                exp = int(time.time()) + token_fields.exp_offset
            token = jwt_token_factory(user_id=token_fields.user_id, exp=exp)

        
        response = auth_service_v0_api_client.filter_notes(token=token, body=case.body)
        assert response.status_code == case.expected_status_code, response.text

        if case.expected_message is not None:
            assert case.expected_message == response.json()[ERROR_FIELD]

        if case.expected_response is not None:
            assert case.expected_response == response.json()