from parameters.auth_service.auth import (
    LOGIN_INVALID_BODY_CASES,
    LOGIN_INVALID_REQUEST_CASES,
    LOGIN_SUCCESS_CASES,
)

from collections.abc import Callable
from typing import Any, ContextManager, Optional

import logging, pytest

from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common.server_error_logging import log_internal_server_error
from src.storages.postgres_client import PostgresClient
from tests.auth_service.api.v0.auth_login_support import postgres_sql_migration
from tests.fixtures.auth_jwt import check_token_fields
from tests.fixtures.vault import LoginSecretBundle
from src.common import fields, audit

logger = logging.getLogger(__name__)

class TestAuthServiceV0Login:
    """Тесты для проверки авторизации"""

    @pytest.mark.parametrize(
        ("req", "expected_fields", "up_sql", "down_sql", "expected_status_code"),
        LOGIN_SUCCESS_CASES,
    )
    def test_success_basic( # noqa: WPS211, WPS231
        self,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        postgres_client: PostgresClient, 
        req: dict[str, str],
        up_sql: str | None,
        down_sql: str | None,
        expected_fields: dict,
        expected_status_code: int,
        get_client_secret: Callable[[str], str],
    ) -> None:
        """
        Тест на успешные запросы на авторизацию.
        Проверяет ответ, payload токена и scope.
        - валидный запрос - 200
        - валидный запрос с множественными scope - 200
        - валидный запрос с пустым scope (но много scope в БД) - 200
        """
        with postgres_sql_migration(postgres_client, up_sql, down_sql):
            assert postgres_client.raw_connection.info is not None
            client_secret = get_client_secret(req["client_id"])
            req["client_secret"] = client_secret

            response = auth_service_v0_api_client.login(req)

            log_internal_server_error(response, logger, fields.ERROR_FIELD)

            assert expected_status_code == response.status_code
            response_data = response.json()

            assert expected_fields[fields.TOKEN_TYPE_FIELD] == response_data[fields.TOKEN_TYPE_FIELD]
            assert expected_fields[fields.EXPIRES_IN_FIELD] == response_data[fields.EXPIRES_IN_FIELD]
            assert expected_fields[fields.SCOPE_FIELD] == response_data[fields.SCOPE_FIELD]

            check_token_fields(
                token=response_data["access_token"],
                expected_fields=expected_fields["token_payload"],
            )

    @pytest.mark.parametrize(
        (
            "req",
            "expected_message",
            "client_id",
            "up_sql",
            "down_sql",
            "login_secret_bundle",
            "expected_status_code",
            "expected_audit_message",
        ),
        LOGIN_INVALID_REQUEST_CASES,
        indirect=["login_secret_bundle"],
    )
    def test_invalid_requests( # noqa: WPS211, WPS231
        self,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        postgres_client: PostgresClient,
        req: dict[str, str],
        up_sql: str | None,
        down_sql: str | None,
        expected_message: str,
        client_id: str,
        expected_status_code: int,
        login_secret_bundle: LoginSecretBundle,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
        expected_audit_message: audit.AuditMessage,
    ) -> None:
        """
        Тест на невалидные запросы на авторизацию.
        - невалидный scope - 403
        - невалидный grant type - 400
        - невалидный client_id - 401
        - неактивный клиент - 401
        - неверный client_secret - 401
        - нет доступа к vault - 500
        """
        with postgres_sql_migration(postgres_client, up_sql, down_sql):
            assert postgres_client.raw_connection.info is not None

            client_secret = login_secret_bundle.get_secret(client_id)
            req["client_secret"] = client_secret

            with login_secret_bundle.around_login(client_id):
                response = auth_service_v0_api_client.login(req)

            log_internal_server_error(response, logger, fields.ERROR_FIELD)

            with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
                    message = rabbitmq_message
            if message:
                real_message = audit.AuditMessage.model_validate_json(message)
                
                audit.assert_audit_message(expected_audit_message, real_message)
                audit.assert_audit_message_context(expected_audit_message, real_message)
            else:
                pytest.fail("Нет сообщений в очереди")

            assert expected_status_code == response.status_code
            assert expected_message == response.json()[fields.ERROR_FIELD]

    @pytest.mark.parametrize( # noqa: WPS211
            (
                "body",
                "expected_message",
                "expected_status_code",
                "expected_audit_message",
            ),
            LOGIN_INVALID_BODY_CASES,
        )
    def test_invalid_body(self, # noqa: WPS211
        auth_service_v0_api_client: AuthServiceV0APIClient,
        body: dict[str, Any],
        expected_message: str,
        expected_status_code: int,
        expected_audit_message: audit.AuditMessage,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """
        Тест на невалидные запросы на авторизацию.
        - пустое тело - 400
        - неправильный json - 400
        - отсутствует client_id - 401
        - неверный client_id - 401
        """
        response = auth_service_v0_api_client.login(body)

        log_internal_server_error(response, logger, fields.ERROR_FIELD)

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message
            if message:
                real_message = audit.AuditMessage.model_validate_json(message)
                
                audit.assert_audit_message(expected_audit_message, real_message)
                audit.assert_audit_message_context(expected_audit_message, real_message)
            else:
                pytest.fail("Нет сообщений в очереди")

        assert expected_status_code == response.status_code
        assert expected_message == response.json()[fields.ERROR_FIELD]
  