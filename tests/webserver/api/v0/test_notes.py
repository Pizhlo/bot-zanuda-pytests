"""
Тесты для проверки работы с заметками
"""

import uuid
from datetime import datetime
from typing import ContextManager, Optional
from zoneinfo import ZoneInfo

import httpx
import pytest

from src.api_clients.webserver import WebServerV0APIClient
from src.models.models import FullMessage, RequestID
from utils.string_generator import generate_long_string, generate_test_string

# Constants for test data keys
USER_ID_FIELD = "user_id"
TEXT_FIELD = "text"
SPACE_ID_FIELD = "space_id"
TYPE_FIELD = "type"
ERROR_FIELD = "error"

# Constants for test data values
TEXT_TYPE = "text"
VALID_SPACE_ID = "869dc163-62aa-4889-9019-07f9c764ce38"
INVALID_SPACE_ID = "6eabae90-5724-4445-84d8-510774bdee03"
USER_ID = 123456789

RANDOM_STRING_LENGTH = 100000

# Constants for test data messages
GENERATED_MSG = generate_long_string(RANDOM_STRING_LENGTH)
GENERATED_MSG_WITH_DIFFERENT_CHARACTERS = generate_test_string(RANDOM_STRING_LENGTH)


class TestWebServerV0Notes:
    """Тесты для проверки работы с заметками"""

    @pytest.mark.parametrize(
        "note,expected_status_code,expected_response,expected_message",
        [
            pytest.param(
                {
                    USER_ID_FIELD: USER_ID,
                    TEXT_FIELD: "Test Note1",
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.ACCEPTED,
                None,
                {
                    USER_ID_FIELD: USER_ID,
                    TEXT_FIELD: "Test Note1",
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                    "operation": "create",
                    "file": "",
                },
                id="create text note success",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: 123456789,
                    TEXT_FIELD: "Test Note2",
                    SPACE_ID_FIELD: INVALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.BAD_REQUEST,
                {ERROR_FIELD: "space not belongs to user"},
                None,
                id="space not belongs to user",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: 123456789,
                    TEXT_FIELD: "Test Note3",
                    SPACE_ID_FIELD: str(uuid.uuid4()),
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.BAD_REQUEST,
                {ERROR_FIELD: "space does not exist"},
                None,
                id="space does not exist",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: 123456789,
                    TEXT_FIELD: "Test Note4",
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                },
                httpx.codes.BAD_REQUEST,
                {ERROR_FIELD: "field `type` not filled"},
                None,
                id="type is required",
            ),
            pytest.param(
                {
                    TEXT_FIELD: "Test Note5",
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.BAD_REQUEST,
                {ERROR_FIELD: "unknown user"},
                None,
                id="field user_id is required",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: 123,
                    TEXT_FIELD: "Test Note6",
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.BAD_REQUEST,
                {ERROR_FIELD: "unknown user"},
                None,
                id="unknown user",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: 123456789,
                    TEXT_FIELD: "Test Note7",
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.BAD_REQUEST,
                {ERROR_FIELD: "space does not exist"},
                None,
                id="space not filled",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: 123456789,
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.BAD_REQUEST,
                {ERROR_FIELD: "field `text` not filled"},
                None,
                id="text not filled",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: 123456789,
                    TEXT_FIELD: "Test Note8",
                    SPACE_ID_FIELD: "1234",
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.BAD_REQUEST,
                {ERROR_FIELD: "invalid UUID length: 4"},
                None,
                id="invalid UUID",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: "1234",
                    TEXT_FIELD: "Test Note9",
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.BAD_REQUEST,
                {
                    ERROR_FIELD: "json: cannot unmarshal string into Go struct field CreateNoteRequest.user_id of type int64"
                },
                None,
                id="invalid type of field user_id",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: 123456789,
                    TEXT_FIELD: 123456,
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.BAD_REQUEST,
                {
                    ERROR_FIELD: "json: cannot unmarshal number into Go struct field CreateNoteRequest.text of type string"
                },
                None,
                id="invalid type of field text",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: 123456789,
                    TEXT_FIELD: "Test Note10",
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: 123456,
                },
                httpx.codes.BAD_REQUEST,
                {
                    ERROR_FIELD: "json: cannot unmarshal number into Go struct field CreateNoteRequest.type of type model.NoteType"
                },
                None,
                id="invalid type of field type",
            ),
            pytest.param(
                None,
                httpx.codes.BAD_REQUEST,
                {ERROR_FIELD: "unexpected end of JSON input"},
                None,
                id="empty JSON",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: 123456789,
                    TEXT_FIELD: GENERATED_MSG,
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.ACCEPTED,
                None,
                {
                    USER_ID_FIELD: 123456789,
                    TEXT_FIELD: GENERATED_MSG,
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                    "operation": "create",
                    "file": "",
                },
                id="very long text",
            ),
            pytest.param(
                {
                    USER_ID_FIELD: 123456789,
                    TEXT_FIELD: GENERATED_MSG_WITH_DIFFERENT_CHARACTERS,
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                },
                httpx.codes.ACCEPTED,
                None,
                {
                    USER_ID_FIELD: 123456789,
                    TEXT_FIELD: GENERATED_MSG_WITH_DIFFERENT_CHARACTERS,
                    SPACE_ID_FIELD: VALID_SPACE_ID,
                    TYPE_FIELD: TEXT_TYPE,
                    "operation": "create",
                    "file": "",
                },
                id="very long text with different characters",
            ),
        ],
    )
    def test_create_note(  # noqa: WPS211, WPS210
        self,
        note_messages_from_rabbitmq: ContextManager[Optional[bytes]],
        webserver_v0_api_client: WebServerV0APIClient,
        note: dict,
        expected_status_code: httpx.codes,
        expected_response: dict | None,
        expected_message: dict | None,
    ) -> None:
        """
        Тест создания заметки с разными сценариями.
        - Успешное создание заметки: 202 Accepted
        - Очень длинный текст: 202 Accepted
        - Пространство не принадлежит пользователю: 400 Bad Request
        - Пространство не существует: 400 Bad Request
        - Не указан тип заметки: 400 Bad Request
        - Не указан user_id: 400 Bad Request
        - Неизвестный пользователь: 400 Bad Request
        - Неизвестное пространство: 400 Bad Request
        - Не указано пространство: 400 Bad Request
        - Не указан текст: 400 Bad Request
        - Неправильный UUID: 400 Bad Request
        - Неправильный тип user_id: 400 Bad Request
        - Неправильный тип text: 400 Bad Request
        - Неправильный тип type: 400 Bad Request
        - Пустой JSON: 400 Bad Request
        """
        response = webserver_v0_api_client.create_note(note)
        assert response.status_code == expected_status_code, response.text
        match expected_status_code:
            case httpx.codes.ACCEPTED:
                RequestID.model_validate(response.json())
                request_id = response.json()["request_id"]

                if expected_message is not None:
                    expected_message["request_id"] = request_id

                full_message = FullMessage.model_validate(expected_message)
                with note_messages_from_rabbitmq as rabbitmq_message:
                    message = rabbitmq_message
                if message:
                    real_message = FullMessage.model_validate_json(message)

                    # не можем знать точное время создания операции, поэтому присваиваем его из сообщения.
                    # дальше проверим разницу между временем создания операции и текущим временем
                    full_message.created = real_message.created
                    assert real_message == full_message

                    # Проверка времени создания сообщения
                    moscow_tz = ZoneInfo("Europe/Moscow")

                    message_time = get_message_time(real_message, moscow_tz)

                    current_time = datetime.now(moscow_tz)

                    check_time_difference(message_time, current_time, 2)

                else:
                    pytest.fail("Нет сообщений")
            case _:
                assert response.json() == expected_response


def check_time_difference(
    message_time: datetime, current_time: datetime, max_allowed_diff: int = 2
) -> None:
    """
    Проверяет разницу между временем создания операции и текущим временем.
    По умолчанию максимальная разница 2 секунды.
    """
    time_diff = abs((current_time - message_time).total_seconds())
    assert time_diff <= max_allowed_diff, (
        f"Time difference {time_diff}s exceeds allowed {max_allowed_diff}s"
    )


def get_message_time(message: FullMessage, tz: ZoneInfo) -> datetime:
    """
    Получает время создания операции из поля created
    """
    if message.created is not None:
        return datetime.fromtimestamp(message.created, tz=tz)

    pytest.fail("Message created timestamp is None")
