import httpx, pytest
from src.common import fields, errors as common_errors, audit

LOGIN_SUCCESS_CASES = (
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
)
"""Тест на успешные запросы на авторизацию.

Проверяет ответ, payload токена и scope.
- валидный запрос - 200
- валидный запрос с множественными scope - 200
- валидный запрос с пустым scope (но много scope в БД) - 200
"""


LOGIN_INVALID_REQUEST_CASES = (
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
)
"""Тест на невалидные запросы на авторизацию.

- невалидный scope - 403
- невалидный grant type - 400
- невалидный client_id - 401
- неактивный клиент - 401
- неверный client_secret - 401
- секрет клиента отсутствует в vault - 401
"""


LOGIN_INVALID_BODY_CASES = (
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
    )
"""Тест на невалидные запросы на авторизацию.

- пустое тело - 400
- неправильный json - 400
- отсутствует client_id - 401
"""
