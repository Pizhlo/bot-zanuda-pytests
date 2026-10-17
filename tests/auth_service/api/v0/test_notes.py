import logging
from collections.abc import Callable
from typing import ContextManager, Optional

import pytest

import src.common.audit as audit
import src.common.fields as fields
from parameters.auth_service.notes import (
    FILTER_NOTES_CASES,
    FILTER_NOTES_INVALID_TOKEN_CASES,
    FilterNotesCase,
    InvalidFilterNotesTokenCase,
)
from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common.server_error_logging import log_internal_server_error
from assertions.auth_service import assert_audit_payload
from tests.fixtures.auth_jwt import optional_token

logger = logging.getLogger(__name__)


class TestAuthServiceV0Notes:
    """Тесты для проверки работы с заметками"""

    @pytest.mark.parametrize(
        ("case", "expected_audit_message"),
        FILTER_NOTES_CASES,
    )
    def test_filter_notes(
        self,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        login: str,
        case: FilterNotesCase,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
        expected_audit_message: audit.AuditMessage,
    ) -> None:
        """Тест на фильтрацию заметок."""
        token = login

        response = auth_service_v0_api_client.filter_notes(
            token=token, body=case.body, x_telegram_user_id=case.x_telegram_user_id
        )
        log_internal_server_error(response, logger, fields.ERROR_FIELD)

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message
        assert_audit_payload(message, expected_audit_message)

        assert response.status_code == case.expected_status_code, response.text

        if case.expected_message is not None:
            assert case.expected_message == response.json()[fields.ERROR_FIELD]

        if case.expected_response is not None:
            assert case.expected_response == response.json()

    @pytest.mark.parametrize(
        ("invalid_case", "expected_audit_message"),
        FILTER_NOTES_INVALID_TOKEN_CASES,
    )
    def test_filter_notes_invalid_token(
        self,
        invalid_case: InvalidFilterNotesTokenCase,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        jwt_token_factory: Callable[..., str],
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """Тест на фильтрацию заметок."""
        token = optional_token(jwt_token_factory, invalid_case.token_fields)

        response = auth_service_v0_api_client.filter_notes(
            token=token,
            body=None,
            x_telegram_user_id=invalid_case.telegram_user_id,
        )

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        assert_audit_payload(message, expected_audit_message)

        assert response.status_code == invalid_case.expected_status_code, response.text

        if invalid_case.expected_message is not None:
            assert invalid_case.expected_message == response.json()[fields.ERROR_FIELD]

        log_internal_server_error(response, logger, fields.ERROR_FIELD)

        if invalid_case.expected_response is not None:
            assert invalid_case.expected_response == response.json()
