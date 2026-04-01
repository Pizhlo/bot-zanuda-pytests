from collections.abc import Callable
from typing import Any

import httpx, logging, pytest  # noqa: E401

from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common.server_error_logging import log_internal_server_error
from src.storages.postgres_client import PostgresClient
from tests.auth_service.api.v0.auth_login_support import postgres_sql_migration
from tests.fixtures.auth_jwt import check_token_fields
from tests.fixtures.vault import LoginSecretBundle

from src.common.fields import (
    CLIENT_ID_BOT,
    ERROR_FIELD,
    EXPIRES_IN_FIELD,
    GRANT_TYPE_CLIENT_CREDENTIALS,
    SCOPE_BOT,
    SCOPE_FIELD,
    SUBJECT_BOT,
    TOKEN_TYPE_FIELD,
)
from src.common.fields import (
    NO_VAULT_SECRET_BUNDLE,
    TOKEN_PAYLOAD_FIELD,
    VAULT_SECRET_BUNDLE,
    WRONG_SECRET_BUNDLE,
)
from src.common.errors import (
    INVALID_GRANT_TYPE_ERROR,
    INVALID_CLIENT_ERROR,
    INACTIVE_CLIENT_ERROR,
)

logger = logging.getLogger(__name__)

class TestAuthServiceV0Login:
    """Тесты для проверки авторизации"""

    @pytest.mark.parametrize(
        ("req", "expected_fields", "up_sql", "down_sql", "expected_status_code"),
        [
            pytest.param(
                dict[str, str](
                    grant_type=GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=CLIENT_ID_BOT,
                    client_secret="",
                    scope=SCOPE_BOT,
                ),
                {
                    TOKEN_TYPE_FIELD: "Bearer",
                    EXPIRES_IN_FIELD: 3600,
                    SCOPE_FIELD: SCOPE_BOT,
                    TOKEN_PAYLOAD_FIELD: {"iss": "zanuda-auth-service", "sub": SUBJECT_BOT, "aud": ["zanuda-internal-api"], EXPIRES_IN_FIELD: 3600},
                },
                None,
                None,
                httpx.codes.OK,
                id="valid request",
            ),
            pytest.param(
                dict[str, str](
                    grant_type=GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=CLIENT_ID_BOT,
                    client_secret="",
                    scope=SCOPE_BOT,
                ),
                {
                    TOKEN_TYPE_FIELD: "Bearer", 
                    EXPIRES_IN_FIELD: 3600,
                    SCOPE_FIELD: SCOPE_BOT,
                    TOKEN_PAYLOAD_FIELD: {"iss": "zanuda-auth-service", "sub": SUBJECT_BOT, "aud": ["zanuda-internal-api"], EXPIRES_IN_FIELD: 3600},
                },
                "UPDATE auth.service_clients SET scopes = ARRAY['bot', 'admin']::text[] WHERE client_id = 'bot'",
                "UPDATE auth.service_clients SET scopes = ARRAY['bot']::text[] WHERE client_id = 'bot'",
                httpx.codes.OK,
                id="valid with many scopes",
            ),
            pytest.param(
                dict[str, str](
                    grant_type=GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=CLIENT_ID_BOT,
                    client_secret="",
                    scope="",
                ),
                {
                    TOKEN_TYPE_FIELD: "Bearer",
                    EXPIRES_IN_FIELD: 3600,
                    SCOPE_FIELD: "bot admin",
                    TOKEN_PAYLOAD_FIELD: {"iss": "zanuda-auth-service", "sub": SUBJECT_BOT, "aud": ["zanuda-internal-api"], EXPIRES_IN_FIELD: 3600},
                },
                "UPDATE auth.service_clients SET scopes = ARRAY['bot', 'admin']::text[] WHERE client_id = 'bot'",
                "UPDATE auth.service_clients SET scopes = ARRAY['bot']::text[] WHERE client_id = 'bot'",
                httpx.codes.OK,
                id="valid with many scopes and empty scope",
            ),
        ],
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

            log_internal_server_error(response, logger, ERROR_FIELD)

            assert expected_status_code == response.status_code
            response_data = response.json()

            assert expected_fields[TOKEN_TYPE_FIELD] == response_data[TOKEN_TYPE_FIELD]
            assert expected_fields[EXPIRES_IN_FIELD] == response_data[EXPIRES_IN_FIELD]
            assert expected_fields[SCOPE_FIELD] == response_data[SCOPE_FIELD]

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
        [
            pytest.param(
                dict[str, str](
                    grant_type=GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=CLIENT_ID_BOT,
                    client_secret="",
                    scope="bot bot admin",
                ),
                "invalid scope",
                CLIENT_ID_BOT,
                None,
                None,
                VAULT_SECRET_BUNDLE,
                httpx.codes.FORBIDDEN,
                id="invalid scope",
            ),
            pytest.param(
                dict[str, str](
                    grant_type="password",
                    client_id=CLIENT_ID_BOT,
                    client_secret="",
                    scope=SCOPE_BOT,
                ),
                "invalid grant type",
                CLIENT_ID_BOT,
                None,
                None,
                VAULT_SECRET_BUNDLE,
                httpx.codes.BAD_REQUEST,
                id="invalid grant type",
            ),
            pytest.param(
                dict[str, str](
                    grant_type=GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id="invalid",
                    client_secret="",
                    scope="",
                ),
                INVALID_CLIENT_ERROR,
                CLIENT_ID_BOT,
                None,
                None,
                VAULT_SECRET_BUNDLE,
                httpx.codes.UNAUTHORIZED,
                id=INVALID_CLIENT_ERROR,
            ),
            pytest.param(
                dict[str, str](
                    grant_type=GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=CLIENT_ID_BOT,
                    client_secret="",
                    scope=SCOPE_BOT,
                ),
                "client is inactive",
                CLIENT_ID_BOT,
                "update auth.service_clients SET is_active = false WHERE client_id = 'bot'",
                "update auth.service_clients SET is_active = true WHERE client_id = 'bot'",
                VAULT_SECRET_BUNDLE,
                httpx.codes.UNAUTHORIZED,
                id=INACTIVE_CLIENT_ERROR,
            ),
            pytest.param(
                dict[str, str](
                    grant_type=GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=CLIENT_ID_BOT,
                    client_secret="",
                    scope=SCOPE_BOT,
                ),
                "invalid client secret",
                CLIENT_ID_BOT,
                None,
                None,
                WRONG_SECRET_BUNDLE,
                httpx.codes.UNAUTHORIZED,
                id="invalid client secret",
            ),
            pytest.param(
                dict[str, str](
                    grant_type=GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=CLIENT_ID_BOT,
                    client_secret="",
                    scope=SCOPE_BOT,
                ),
                "internal server error",
                CLIENT_ID_BOT,
                None,
                None,
                NO_VAULT_SECRET_BUNDLE,
                httpx.codes.INTERNAL_SERVER_ERROR,
                id="no vault client secret",
            ),
        ],
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

            log_internal_server_error(response, logger, ERROR_FIELD)

            assert expected_status_code == response.status_code
            assert expected_message == response.json()[ERROR_FIELD]

    @pytest.mark.parametrize(
            (
                "body",
                "expected_message",
                "expected_status_code",
            ),
            [
                pytest.param(
                    dict[str, str](),
                    INVALID_GRANT_TYPE_ERROR,
                    httpx.codes.BAD_REQUEST,
                    id="empty body",
                ),
                 pytest.param(
                    {"invalid-json": "invalid-json"},
                    INVALID_GRANT_TYPE_ERROR,
                    httpx.codes.BAD_REQUEST,
                    id="invalid json",
                ),
                pytest.param(
                    {"grant_type":"client_credentials","client_secret":"x"},
                    INVALID_CLIENT_ERROR,
                    httpx.codes.UNAUTHORIZED,
                    id="invalid client",
                )
            ],
        )
    def test_invalid_body(self, 
        auth_service_v0_api_client: AuthServiceV0APIClient,
        body: dict[str, Any],
        expected_message: str,
        expected_status_code: int,
    ) -> None:
        """
        Тест на невалидные запросы на авторизацию.
        - пустое тело - 400
        - неправильный json - 400
        - отсутствует client_id - 401
        - неверный client_id - 401
        """
        response = auth_service_v0_api_client.login(body)

        log_internal_server_error(response, logger, ERROR_FIELD)

        assert expected_status_code == response.status_code
        assert expected_message == response.json()[ERROR_FIELD]