import httpx, pytest
from src.common import fields, errors as common_errors

# Для POST /api/v0/auth/login единое событие аудита HTTP-запроса появится в отдельной задаче.
# Прежние проверки ошибок ожидали события внутренних операций логина. Сейчас проверяем
# HTTP-ответ и выданный JWT. Когда маршрут начнёт записывать итог запроса, добавим
# проверки аудита для успешного логина и для отказов.
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
"""Выдача токена сервисному клиенту по client_credentials.

- Клиенту выдан scope bot, и он запрашивает bot: 200 OK, Bearer-токен со scope bot.
- Клиенту выданы bot и admin, он запрашивает только bot: 200 OK, в ответе только bot.
- Клиенту выданы bot и admin, он оставляет scope пустым: 200 OK, в ответе оба scope.
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
        id="no vault client secret",
    ),
)
"""Отказы при выдаче токена сервисному клиенту.

- Клиент запрашивает «bot bot admin», хотя ему выдан только bot: 403 Forbidden.
- Передан grant_type=password: 400 Bad Request.
- Передан неизвестный client_id: 401 Unauthorized.
- Клиент выключен в PostgreSQL: 401 Unauthorized.
- Секрет из запроса не совпадает с секретом клиента: 401 Unauthorized.
- В Vault отсутствует секрет этого клиента: 401 Unauthorized.
"""


LOGIN_INVALID_BODY_CASES = (
        pytest.param(
            dict[str, str](),
            common_errors.EMPTY_LOGIN_REQUEST_ERROR,
            httpx.codes.BAD_REQUEST,
            id="empty body",
        ),
         pytest.param(
            {"invalid-json": "invalid-json"},
            common_errors.EMPTY_LOGIN_REQUEST_ERROR,
            httpx.codes.BAD_REQUEST,
            id="invalid json",
        ),
        pytest.param(
            {"grant_type":"client_credentials","client_secret":"x"},
            common_errors.INVALID_CLIENT_ERROR,
            httpx.codes.UNAUTHORIZED,
            id="invalid client",
        )
    )
"""Ошибки тела запроса на выдачу токена.

- Передан пустой JSON-объект: 400 Bad Request.
- Передан JSON-объект только с неизвестным полем invalid-json: 400 Bad Request.
- Указаны grant_type и client_secret, пропущен client_id: 401 Unauthorized.
"""
