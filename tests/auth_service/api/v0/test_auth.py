import logging
from typing import Any, Callable

import pytest

from parameters.auth_service.auth import (
    LOGIN_INVALID_BODY_CASES,
    LOGIN_INVALID_REQUEST_CASES,
    LOGIN_SUCCESS_CASES,
)
from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common import fields
from src.common.server_error_logging import log_internal_server_error
from src.storages.postgres_client import PostgresClient
from tests.auth_service.api.v0.auth_login_support import postgres_sql_migration
from tests.fixtures.auth_jwt import check_token_fields
from tests.fixtures.vault import LoginSecretBundle

logger = logging.getLogger(__name__)


class TestAuthServiceV0Login:
    """Тесты для проверки авторизации"""

    @pytest.mark.parametrize(
        ("req", "expected_fields", "up_sql", "down_sql", "expected_status_code"),
        LOGIN_SUCCESS_CASES,
    )
    def test_success_basic(  # noqa: WPS211, WPS231
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
        """Получает JWT для сервисного клиента по секрету из Vault.
        Проверяет тип, срок действия, выданный scope и подписанные поля токена.
        """
        with postgres_sql_migration(postgres_client, up_sql, down_sql):
            assert postgres_client.raw_connection.info is not None
            client_secret = get_client_secret(req["client_id"])
            req = {**req, "client_secret": client_secret}

            response = auth_service_v0_api_client.login(req)

            log_internal_server_error(response, logger, fields.ERROR_FIELD)

            assert expected_status_code == response.status_code
            response_data = response.json()

            assert (
                expected_fields[fields.TOKEN_TYPE_FIELD]
                == response_data[fields.TOKEN_TYPE_FIELD]
            )
            assert (
                expected_fields[fields.EXPIRES_IN_FIELD]
                == response_data[fields.EXPIRES_IN_FIELD]
            )
            assert (
                expected_fields[fields.SCOPE_FIELD] == response_data[fields.SCOPE_FIELD]
            )

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
        ),
        LOGIN_INVALID_REQUEST_CASES,
        indirect=["login_secret_bundle"],
    )
    def test_invalid_requests(  # noqa: WPS211, WPS231
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
    ) -> None:
        """Проверяет отказ в выдаче токена при неверных реквизитах, состоянии клиента или параметрах доступа.

        Неизвестный или отключённый клиент, неверный секрет и отсутствие секрета в Vault приводят к 401 Unauthorized.
        Неподдерживаемый grant_type даёт 400 Bad Request, а попытка получить невыданные права — 403 Forbidden.
        """
        with postgres_sql_migration(postgres_client, up_sql, down_sql):
            assert postgres_client.raw_connection.info is not None

            client_secret = login_secret_bundle.get_secret(client_id)
            req = {**req, "client_secret": client_secret}

            with login_secret_bundle.around_login(client_id):
                response = auth_service_v0_api_client.login(req)

            log_internal_server_error(response, logger, fields.ERROR_FIELD)


            assert expected_status_code == response.status_code
            assert expected_message == response.json()[fields.ERROR_FIELD]

    @pytest.mark.parametrize(  # noqa: WPS211
        (
            "body",
            "expected_message",
            "expected_status_code",
        ),
        LOGIN_INVALID_BODY_CASES,
    )
    def test_invalid_body(  # noqa: WPS211
        self,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        body: dict[str, Any],
        expected_message: str,
        expected_status_code: int,
    ) -> None:
        """Проверяет, как сервис отвечает на неполный запрос о выдаче токена.

        Пустой объект и объект с одним неизвестным полем дают 400 Bad Request. Если переданы секрет и grant_type,
        но отсутствует идентификатор клиента, сервис отвечает 401 Unauthorized.
        """
        response = auth_service_v0_api_client.login(body)

        log_internal_server_error(response, logger, fields.ERROR_FIELD)


        assert expected_status_code == response.status_code
        assert expected_message == response.json()[fields.ERROR_FIELD]
