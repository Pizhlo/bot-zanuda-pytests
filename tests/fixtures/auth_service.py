from collections.abc import Callable
from functools import partial

import pytest

from src.api_clients.auth_service import AuthServiceAPIClient, AuthServiceV0APIClient
from src.config import config
from tests.fixtures.auth_jwt import make_jwt_token


def wrong_client_secret_for_login(_client_id: str) -> str:
    """Секрет, заведомо не совпадающий с Vault/БД (негативные тесты login)."""
    return "__pytest_invalid_client_secret__"


@pytest.fixture()
def wrong_client_secret() -> Callable[[str], str]:
    """Возвращает функцию с неверным client_secret для подстановки в запрос."""
    return wrong_client_secret_for_login


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
