from collections.abc import Callable
from typing import Any, ContextManager, Optional

import httpx, logging, pytest

from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common.server_error_logging import log_internal_server_error
from src.storages.postgres_client import PostgresClient
from tests.auth_service.api.v0.auth_login_support import postgres_sql_migration
from tests.fixtures.auth_jwt import check_token_fields
from tests.fixtures.vault import LoginSecretBundle
from src.common import fields, errors as common_errors, audit

logger = logging.getLogger(__name__)

class TestAuthServiceV0Login:
    """Тесты для проверки авторизации"""

    @pytest.mark.parametrize(
        ("req", "expected_fields", "up_sql", "down_sql", "expected_status_code"),
        [
            pytest.param(
                dict[str, str](
                    grant_type=fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=fields.CLIENT_ID_BOT,
                    client_secret="",
                    scope=fields.SCOPE_BOT,
                ),
                {
                    fields.TOKEN_TYPE_FIELD: "Bearer",
                    fields.EXPIRES_IN_FIELD: 3600,
                    fields.SCOPE_FIELD: fields.SCOPE_BOT,
                    fields.TOKEN_PAYLOAD_FIELD: {"iss": "zanuda-auth-service", "sub": fields.SUBJECT_BOT, "aud": ["zanuda-internal-api"], fields.EXPIRES_IN_FIELD: 3600},
                },
                None,
                None,
                httpx.codes.OK,
                id="valid request",
            ),
            pytest.param(
                dict[str, str](
                    grant_type=fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=fields.CLIENT_ID_BOT,
                    client_secret="",
                    scope=fields.SCOPE_BOT,
                ),
                {
                    fields.TOKEN_TYPE_FIELD: "Bearer", 
                    fields.EXPIRES_IN_FIELD: 3600,
                    fields.SCOPE_FIELD: fields.SCOPE_BOT,
                    fields.TOKEN_PAYLOAD_FIELD: {"iss": "zanuda-auth-service", "sub": fields.SUBJECT_BOT, "aud": ["zanuda-internal-api"], fields.EXPIRES_IN_FIELD: 3600},
                },
                "UPDATE auth.service_clients SET scopes = ARRAY['bot', 'admin']::text[] WHERE client_id = 'bot'",
                "UPDATE auth.service_clients SET scopes = ARRAY['bot']::text[] WHERE client_id = 'bot'",
                httpx.codes.OK,
                id="valid with many scopes",
            ),
            pytest.param(
                dict[str, str](
                    grant_type=fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=fields.CLIENT_ID_BOT,
                    client_secret="",
                    scope="",
                ),
                {
                    fields.TOKEN_TYPE_FIELD: "Bearer",
                    fields.EXPIRES_IN_FIELD: 3600,
                    fields.SCOPE_FIELD: "bot admin",
                    fields.TOKEN_PAYLOAD_FIELD: {"iss": "zanuda-auth-service", "sub": fields.SUBJECT_BOT, "aud": ["zanuda-internal-api"], fields.EXPIRES_IN_FIELD: 3600},
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
        [
            pytest.param(
                dict[str, str](
                    grant_type=fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=fields.CLIENT_ID_BOT,
                    client_secret="",
                    scope="bot bot admin",
                ),
                "invalid scope",
                fields.CLIENT_ID_BOT,
                None,
                None,
                fields.VAULT_SECRET_BUNDLE,
                httpx.codes.FORBIDDEN,
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.ERROR,
                    error_code=audit.ErrorCode.INVALID_SCOPE,
                    cause="invalid scope",
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.AUTH_SERVICE_LOGIN_WITH_CLIENT_CREDENTIALS,
                    status=audit.Status.FAILED,
                    context={
                        fields.CLIENT_ID_FIELD: fields.CLIENT_ID_BOT,
                        fields.GRANT_TYPE_FIELD: fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                        fields.SCOPE_FIELD: "bot bot admin",
                        fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT
                    },
                ),
                id="invalid scope",
            ),
            pytest.param(
                dict[str, str](
                    grant_type=fields.GRANT_TYPE_PASSWORD,
                    client_id=fields.CLIENT_ID_BOT,
                    client_secret="",
                    scope=fields.SCOPE_BOT,
                ),
                "invalid grant type",
                fields.CLIENT_ID_BOT,
                None,
                None,
                fields.VAULT_SECRET_BUNDLE,
                httpx.codes.BAD_REQUEST,
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.WARN,
                    error_code=audit.ErrorCode.INVALID_GRANT_TYPE,
                    cause="invalid grant type",
                    kind=audit.Kind.VALIDATION,
                    operation=audit.Operation.AUTH_SERVICE_LOGIN,
                    status=audit.Status.FAILED,
                    context={
                        fields.CLIENT_ID_FIELD: fields.CLIENT_ID_BOT,
                        fields.GRANT_TYPE_FIELD: fields.GRANT_TYPE_PASSWORD,
                        fields.SCOPE_FIELD: fields.SCOPE_BOT,
                        fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT
                    },
                ),
                id="invalid grant type",
            ),
            pytest.param(
                dict[str, str](
                    grant_type=fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id="invalid",
                    client_secret="",
                    scope="",
                ),
                common_errors.INVALID_CLIENT_ERROR,
                fields.CLIENT_ID_BOT,
                None,
                None,
                fields.VAULT_SECRET_BUNDLE,
                httpx.codes.UNAUTHORIZED,
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.ERROR,
                    error_code=audit.ErrorCode.SERVICE_NOT_FOUND,
                    cause="not found",
                    kind=audit.Kind.DOMAIN,
                     message=audit.Message.UNKNOWN_SERVICE_CLIENT,
                    operation=audit.Operation.AUTH_SERVICE_LOGIN_WITH_CLIENT_CREDENTIALS,
                    status=audit.Status.FAILED,
                    context={
                        fields.CLIENT_ID_FIELD: "invalid",
                        fields.GRANT_TYPE_FIELD: fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                        fields.SCOPE_FIELD: "",
                        fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT
                    },
                ),
                id=common_errors.INVALID_CLIENT_ERROR,
            ),
            pytest.param(
                dict[str, str](
                    grant_type=fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=fields.CLIENT_ID_BOT,
                    client_secret="",
                    scope=fields.SCOPE_BOT,
                ),
                "client is inactive",
                fields.CLIENT_ID_BOT,
                "update auth.service_clients SET is_active = false WHERE client_id = 'bot'",
                "update auth.service_clients SET is_active = true WHERE client_id = 'bot'",
                fields.VAULT_SECRET_BUNDLE,
                httpx.codes.UNAUTHORIZED,
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.ERROR,
                    error_code=audit.ErrorCode.CLIENT_INACTIVE,
                    cause="client is inactive",
                    message=audit.Message.INACTIVE_CLIENT,
                    kind=audit.Kind.DOMAIN,
                    operation=audit.Operation.AUTH_SERVICE_LOGIN_WITH_CLIENT_CREDENTIALS,
                    status=audit.Status.FAILED,
                    context={
                        fields.CLIENT_ID_FIELD: fields.CLIENT_ID_BOT,
                        fields.GRANT_TYPE_FIELD: fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                        fields.SCOPE_FIELD: fields.SCOPE_BOT,
                        fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT
                    },
                ),
                id=common_errors.INACTIVE_CLIENT_ERROR,
            ),
            pytest.param(
                dict[str, str](
                    grant_type=fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=fields.CLIENT_ID_BOT,
                    client_secret="",
                    scope=fields.SCOPE_BOT,
                ),
                common_errors.INVALID_CLIENT_SECRET_ERROR,
                fields.CLIENT_ID_BOT,
                None,
                None,
                fields.WRONG_SECRET_BUNDLE,
                httpx.codes.UNAUTHORIZED,
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.WARN,
                    error_code=audit.ErrorCode.INVALID_SECRET,
                    cause=common_errors.INVALID_CLIENT_SECRET_ERROR,
                    message=audit.Message.INVALID_CLIENT_SECRET,
                    kind=audit.Kind.DOMAIN,
                    operation=audit.Operation.AUTH_SERVICE_LOGIN_WITH_CLIENT_CREDENTIALS,
                    status=audit.Status.FAILED,
                    context={
                        fields.CLIENT_ID_FIELD: fields.CLIENT_ID_BOT,
                        fields.GRANT_TYPE_FIELD: fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                        fields.SCOPE_FIELD: fields.SCOPE_BOT,
                        fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT
                    },
                ),
                id=common_errors.INVALID_CLIENT_SECRET_ERROR,
            ),
            pytest.param(
                dict[str, str](
                    grant_type=fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                    client_id=fields.CLIENT_ID_BOT,
                    client_secret="",
                    scope=fields.SCOPE_BOT,
                ),
                "invalid client secret",
                fields.CLIENT_ID_BOT,
                None,
                None,
                fields.NO_VAULT_SECRET_BUNDLE,
                httpx.codes.UNAUTHORIZED,
                audit.AuditMessage(
                    service_name=audit.AUTH_SERVICE_NAME,
                    level=audit.Level.ERROR,
                    error_code=audit.ErrorCode.VAULT_SECRET_NOT_FOUND,
                    cause="client secret not found in vault",
                    kind=audit.Kind.INFRASTRUCTURE,
                    operation=audit.Operation.AUTH_SERVICE_LOGIN_WITH_CLIENT_CREDENTIALS,
                    status=audit.Status.FAILED,
                    message=audit.Message.NOT_FOUND_VAULT_SECRET,
                    context={
                        fields.CLIENT_ID_FIELD: fields.CLIENT_ID_BOT,
                        fields.GRANT_TYPE_FIELD: fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                        fields.SCOPE_FIELD: fields.SCOPE_BOT,
                        fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT
                    },
                ),
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
            [
                pytest.param(
                    dict[str, str](),
                    common_errors.EMPTY_LOGIN_REQUEST_ERROR,
                    httpx.codes.BAD_REQUEST,
                    audit.AuditMessage(
                        service_name=audit.AUTH_SERVICE_NAME,
                        level=audit.Level.WARN,
                        error_code=audit.ErrorCode.EMPTY_LOGIN_REQUEST,
                        cause="empty login request",
                        kind=audit.Kind.VALIDATION,
                        message=audit.Message.EMPTY_LOGIN_REQUEST,
                        operation=audit.Operation.AUTH_SERVICE_LOGIN,
                        status=audit.Status.FAILED,
                        context={
                            fields.CLIENT_ID_FIELD: "",
                            fields.GRANT_TYPE_FIELD: "",
                            fields.SCOPE_FIELD: "",
                            fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT,
                    },
                    ),
                    id="empty body",
                ),
                 pytest.param(
                    {"invalid-json": "invalid-json"},
                    common_errors.EMPTY_LOGIN_REQUEST_ERROR,
                    httpx.codes.BAD_REQUEST,
                    audit.AuditMessage(
                       service_name=audit.AUTH_SERVICE_NAME,
                        level=audit.Level.WARN,
                        error_code=audit.ErrorCode.EMPTY_LOGIN_REQUEST,
                        cause="empty login request",
                        kind=audit.Kind.VALIDATION,
                        message=audit.Message.EMPTY_LOGIN_REQUEST,
                        operation=audit.Operation.AUTH_SERVICE_LOGIN,
                        status=audit.Status.FAILED,
                        context={
                            fields.CLIENT_ID_FIELD: "",
                            fields.GRANT_TYPE_FIELD: "",
                            fields.SCOPE_FIELD: "",
                            fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT,
                        },
                    ),
                    id="invalid json",
                ),
                pytest.param(
                    {"grant_type":"client_credentials","client_secret":"x"},
                    common_errors.INVALID_CLIENT_ERROR,
                    httpx.codes.UNAUTHORIZED,
                    audit.AuditMessage(
                        service_name=audit.AUTH_SERVICE_NAME,
                        level=audit.Level.ERROR,
                        error_code=audit.ErrorCode.SERVICE_NOT_FOUND,
                        cause="not found",
                        message=audit.Message.UNKNOWN_SERVICE_CLIENT,
                        kind=audit.Kind.DOMAIN,
                        status=audit.Status.FAILED,
                        operation=audit.Operation.AUTH_SERVICE_LOGIN_WITH_CLIENT_CREDENTIALS,
                         context={
                            fields.CLIENT_ID_FIELD: "",
                            fields.GRANT_TYPE_FIELD: fields.GRANT_TYPE_CLIENT_CREDENTIALS,
                            fields.SCOPE_FIELD: "",
                            fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT,
                        },
                    ),
                    id="invalid client",
                )
            ],
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
  