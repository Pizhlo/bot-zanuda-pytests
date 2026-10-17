import uuid
import httpx
import pytest
from utils.string_generator import generate_long_string, generate_test_string

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


NOTE_CREATE_CASES = (
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
)
"""Тест создания заметки с разными сценариями.

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
