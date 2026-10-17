"""
Тесты для проверки работы с заметками
"""

from typing import ContextManager, Optional

import httpx
import pytest

from parameters.webserver.notes import (
    NOTE_CREATE_CASES,
)
from src.api_clients.webserver import WebServerV0APIClient
from src.models.models import FullMessage, RequestID
from assertions.webserver import assert_note_message


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
        """Тест создания заметки с разными сценариями."""
        response = webserver_v0_api_client.create_note(note)
        assert response.status_code == expected_status_code, response.text
        match expected_status_code:
            case httpx.codes.ACCEPTED:
                RequestID.model_validate(response.json())
                request_id = response.json()["request_id"]

                if expected_message is not None:
                    expected_message = {**expected_message, "request_id": request_id}

                full_message = FullMessage.model_validate(expected_message)
                with note_messages_from_rabbitmq as rabbitmq_message:
                    assert_note_message(rabbitmq_message, full_message)
            case _:
                assert response.json() == expected_response
