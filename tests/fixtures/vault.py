from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from src.config import config
from src.storages.vault_client import VaultClient


@dataclass(frozen=True)
class LoginSecretBundle:
    """
    Как получить ``client_secret`` для тела login и что обернуть вокруг HTTP-вызова.

    Строковые режимы задаются в ``@pytest.mark.parametrize(..., indirect=["login_secret_bundle"])``.
    """

    get_secret: Callable[[str], str]
    around_login: Callable[[str], AbstractContextManager[None]]


@pytest.fixture()
def login_secret_bundle(
    request: pytest.FixtureRequest,
    get_client_secret: Callable[[str], str],
    get_client_secret_without_vault: Callable[[str], str],
    vault_empty_for_client: Callable[[str], AbstractContextManager[None]],
    wrong_client_secret: Callable[[str], str],
) -> LoginSecretBundle:
    mode: str = request.param
    if mode == "vault":
        return LoginSecretBundle(
            get_secret=get_client_secret,
            around_login=lambda _cid: nullcontext(),
        )
    if mode == "wrong":
        return LoginSecretBundle(
            get_secret=wrong_client_secret,
            around_login=lambda _cid: nullcontext(),
        )
    if mode == "no_vault":
        return LoginSecretBundle(
            get_secret=get_client_secret_without_vault,
            around_login=vault_empty_for_client,
        )
    raise ValueError(f"unknown login_secret_bundle mode: {mode!r}")


@pytest.fixture()
def get_client_secret_without_vault() -> Callable[[str], str]:
    """
    Секрет только для тела login-запроса — **без обращения к Vault**.

    Нужен, когда в Vault секрета нет (или вы его временно удалили): тест не падает
    на 404, а **auth-сервис** сам ходит в Vault и получает ответ «не найдено».
    """
    return lambda _client_id: "__pytest_client_secret_without_vault__"


@contextmanager
def vault_secret_removed_for_client(
    vault_client: VaultClient,
    client_id: str,
) -> Generator[None, None, None]:
    """
    На время блока убирает секрет KV по ``auth_clients_path/<client_id>``,
    после выхода восстанавливает прежние данные (если они были).
    """
    auth_base = config.vault.auth_clients_path.strip("/")
    path = f"{auth_base}/{client_id}"
    backup: dict[str, Any] | None = None
    try:
        backup = vault_client.read_secret(path)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != httpx.codes.NOT_FOUND:
            raise
    if backup is not None:
        vault_client.delete_secret_metadata(path)
    try:
        yield
    finally:
        if backup is not None:
            vault_client.write_secret(path, backup)


@pytest.fixture()
def vault_empty_for_client(
    vault_client: VaultClient,
) -> Callable[[str], AbstractContextManager[None]]:
    """
    Возвращает контекстный менеджер ``with vault_empty_for_client(cid): ...`` —
    на время теста секрет в Vault для этого client_id отсутствует.
    """
    return lambda client_id: vault_secret_removed_for_client(vault_client, client_id)


@pytest.fixture(scope="session")
def vault_client() -> Generator[VaultClient, None, None]:
    """Клиент Vault для чтения тестовых секретов."""
    with VaultClient(
        base_url=str(config.vault.base_url),
        token=config.vault.token,
        timeout=config.vault.timeout,
        mount_point=config.vault.mount_point,
    ) as client:
        yield client


@pytest.fixture(scope="session")
def get_client_secret(vault_client: VaultClient) -> Callable[[str], str]:
    """Фикстура для получения client_secret по client_id."""
    return lambda client_id: vault_client.get_client_secret(
        client_id,
        secrets_path=config.vault.auth_clients_path,
    )