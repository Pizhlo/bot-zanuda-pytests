import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

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

# ID LISTS
MAX_NOTE_ID = 1000 # максимальнай айди заметки. на самом деле может быть любым, но для тестов я взяла такой.
BIG_LIST_WITHOUT_EXISTING_NOTES = list[int](range(4, MAX_NOTE_ID))  # детерминированный список без 1, 2, 3
BIG_LIST_WITH_EXISTING_NOTES = BIG_LIST_WITHOUT_EXISTING_NOTES + [1, 2, 3]

# детерминированный пользователь, которого нет в базе фикстур
NON_MEMBER_USER_ID = 10_000_000


@dataclass(frozen=True)
class TokenFields:
    """Параметры, из которых собирается payload токена."""
    user_id: int | None = None
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
                    token_fields=TokenFields(user_id=1, exp_offset=-ONE_HOUR_SECONDS),
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
                    token_fields=TokenFields(user_id=1, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: [1, 2, 3], SPACE_ID_FIELD: -1},
                    expected_status_code=httpx.codes.BAD_REQUEST,
                    expected_response=None,
                    expected_message="empty space id",
                ),
                id="space_id < 1",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=1, exp_offset=ONE_HOUR_SECONDS),
                    body={SPACE_ID_FIELD: 1},
                    expected_status_code=httpx.codes.BAD_REQUEST,
                    expected_response=None,
                    expected_message="empty note id list",
                ),
                id="note_ids is empty",
            ),
             pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=NON_MEMBER_USER_ID, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: [1, 2, 3], SPACE_ID_FIELD: 1},
                    expected_status_code=httpx.codes.FORBIDDEN,
                    expected_response=None,
                    expected_message="user is not member",
                ),
                id="user is not member",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=1, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: [1, 2, 3], SPACE_ID_FIELD: 1},
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            "1": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            "2": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            "3": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="valid request: only real IDs",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=1, exp_offset=ONE_HOUR_SECONDS),
                    body={
                        NOTE_IDS_FIELD: [1, 2, 3, 5, 100, 10000, 4566, 2112, 5343543, 123],
                        SPACE_ID_FIELD: 1,
                    },
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            "1": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            "2": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            "3": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="valid request: real + not real IDs",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=1, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: [5, 100, 10000, 4566, 2112, 5343543, 123], SPACE_ID_FIELD: 1},
                    expected_status_code=httpx.codes.OK,
                    expected_response={NOTES_FIELD: {}},
                    expected_message=None,
                ),
                id="valid request: only not real IDs",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=1, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: BIG_LIST_WITHOUT_EXISTING_NOTES, SPACE_ID_FIELD: 1},
                    expected_status_code=httpx.codes.OK,
                    expected_response={NOTES_FIELD: {}},
                    expected_message=None,
                ),
                id="valid request: generated 1000 IDs (without existing notes)",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=1, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_NOTES, SPACE_ID_FIELD: 1},
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            "1": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            "2": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            "3": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="valid request: generated 1000 IDs",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=2, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: [4, 5, 6], SPACE_ID_FIELD: 2},
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            "4": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            "5": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            "6": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="user=EDITOR, notes=SPACE (only existing notes)",
            ),
            pytest.param(
                FilterNotesCase(
                    token_fields=TokenFields(user_id=2, exp_offset=ONE_HOUR_SECONDS),
                    body={NOTE_IDS_FIELD: BIG_LIST_WITH_EXISTING_NOTES, SPACE_ID_FIELD: 2},
                    expected_status_code=httpx.codes.OK,
                    expected_response={
                        NOTES_FIELD: {
                            "4": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            "5": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                            "6": {CAN_READ_FIELD: True, CAN_EDIT_FIELD: True},
                        }
                    },
                    expected_message=None,
                ),
                id="user=EDITOR, notes=SPACE (existing notes+not existing)",
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
        - space_id < 1 - 400
        - не указаны note_ids - 400
        - пользователь не участвует в пространстве - 403
        - валидный запрос с заметками которые существуют - 200 + список айди из запроса
        - валидный запрос с заметками которые существуют + которые не существуют - 200 + список которые существуют
        - валидный запрос только с заметками которых нет - 200 + пустой список
        - валидный запрос с большим количеством айди заметок (существуют + не существуют) - 200 + список из тех которые существуют
        - валидный запрос с большим количеством айди заметок (не существуют) - 200 + пустой список
        - пользователь - EDITOR, получить все SPACE заметки (только существующие: [4, 5, 6])
        - пользователь - EDITOR, получить все SPACE заметки (существующие + рандомные: [4, 5, 6, ...])
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