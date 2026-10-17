from parameters.auth_service.notes import (
    FILTER_NOTES_CASES,
    FILTER_NOTES_INVALID_TOKEN_CASES,
    FilterNotesCase,
    InvalidFilterNotesTokenCase,
)

import logging
from collections.abc import Callable

import pytest
from src.common.server_error_logging import log_internal_server_error
from src.api_clients.auth_service import AuthServiceV0APIClient
import src.common.audit as audit

import src.common.fields as fields

from typing import ContextManager, Optional

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

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message
        if message and expected_audit_message is not None:
            real_message = audit.AuditMessage.model_validate_json(message)

            audit.assert_audit_message(expected_audit_message, real_message)
            audit.assert_audit_message_context(expected_audit_message, real_message)
        elif expected_audit_message is not None:
            pytest.fail("Нет сообщений в очереди")

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

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        if message and expected_audit_message is not None:
            real_message = audit.AuditMessage.model_validate_json(message)
            audit.assert_audit_message(expected_audit_message, real_message)
            audit.assert_audit_message_context(expected_audit_message, real_message)
        elif expected_audit_message is not None:
            pytest.fail("Нет сообщений в очереди")


        assert response.status_code == invalid_case.expected_status_code, response.text

        if invalid_case.expected_message is not None:
            assert invalid_case.expected_message == response.json()[fields.ERROR_FIELD]

        log_internal_server_error(response, logger, fields.ERROR_FIELD)

        if invalid_case.expected_response is not None:
            assert invalid_case.expected_response == response.json()
