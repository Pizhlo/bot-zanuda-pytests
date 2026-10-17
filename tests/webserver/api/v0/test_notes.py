"""
Тесты для проверки работы с заметками
"""

from parameters.webserver.notes import (
    NOTE_CREATE_CASES,
)



from datetime import datetime
from typing import ContextManager, Optional
from zoneinfo import ZoneInfo

import httpx
import pytest

from src.api_clients.webserver import WebServerV0APIClient
from src.models.models import FullMessage, RequestID

class TestWebServerV0Notes:
    """Тесты для проверки работы с заметками"""

    @pytest.mark.parametrize(
        "note,expected_status_code,expected_response,expected_message",
        NOTE_CREATE_CASES,
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
        if expected_status_code == httpx.codes.ACCEPTED:
            RequestID.model_validate(response.json())
            request_id = response.json()["request_id"]

            if expected_message is not None:
                expected_message["request_id"] = request_id

            full_message = FullMessage.model_validate(expected_message)
            with note_messages_from_rabbitmq as message:
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
        else:
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
