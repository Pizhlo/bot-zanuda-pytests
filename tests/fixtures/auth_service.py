import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from typing import Any

from src.api_clients.auth_service import AuthServiceAPIClient, AuthServiceV0APIClient
from src.config import config
import pytest


_JWT_HEADER_JSON = b'{"alg":"HS256","typ":"JWT"}'


def _base64url(raw: bytes) -> str:
    """Кодирует байты в base64url без паддинга."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _jwt_hs256(payload: dict[str, Any], secret: str) -> str:
    """Собирает и подписывает JWT токен с алгоритмом HS256."""
    header_part = _base64url(_JWT_HEADER_JSON)
    payload_json = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    payload_part = _base64url(payload_json)

    signing_input = f"{header_part}.{payload_part}".encode()
    signature_part = _base64url(
        hmac.new(secret.encode(), signing_input, hashlib.sha256).digest(),
    )
    return f"{header_part}.{payload_part}.{signature_part}"


def make_jwt_token(
    *,
    secret_key: str,
    user_id: int | None = None,
    exp: int | datetime | None = None,
) -> str:
    """
    Генерирует JWT токен для сервиса авторизации.

    Поля добавляются в payload только если переданы:
    - user_id — идентификатор пользователя;
    - exp — unix-время истечения (int) или datetime.
    """
    payload: dict[str, object] = {}

    if user_id is not None:
        payload["user_id"] = user_id

    if exp is not None:
        if isinstance(exp, datetime):
            exp_dt = exp
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            payload["exp"] = int(exp_dt.timestamp())
        else:
            payload["exp"] = exp

    return _jwt_hs256(payload=payload, secret=secret_key)


@pytest.fixture()
def jwt_token_factory() -> Callable[..., str]:
    """Фабрика JWT токенов, использующая секретный ключ из конфига."""
    return partial(make_jwt_token, secret_key=str(config.auth_service.secret_key))


@pytest.fixture(scope="session")
def auth_service_v0_api_client() -> AuthServiceV0APIClient:
    return AuthServiceV0APIClient()


@pytest.fixture(scope="session")
def auth_service_api_client() -> AuthServiceAPIClient:
    return AuthServiceAPIClient()