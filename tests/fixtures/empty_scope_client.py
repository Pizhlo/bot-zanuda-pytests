"""Отдельный активный клиент без разрешений для проверки цепочки login → decisions/check."""

from collections.abc import Iterator
from contextlib import ExitStack
from uuid import uuid4

import httpx
import pytest

from src.config import config
from src.storages.postgres_client import PostgresClient
from src.storages.vault_client import VaultClient


@pytest.fixture()
def empty_scope_credentials(
    postgres_client: PostgresClient, vault_client: VaultClient
) -> Iterator[dict[str, str]]:
    """Регистрирует активного клиента без прав с отдельным секретом для штатного login."""
    client, secret = str(uuid4()), str(uuid4())
    path = f"{config.vault.auth_clients_path.strip('/')}/{client}"
    with ExitStack() as cleanup:
        cleanup.callback(
            postgres_client.execute,
            "DELETE FROM auth.service_clients WHERE client_id = %s",
            (client,),
        )
        cleanup.callback(remove_client_secret, vault_client, path)
        vault_client.write_secret(path, {"api_key": secret})
        postgres_client.execute(
            "INSERT INTO auth.service_clients(client_id, client_name, scopes) VALUES (%s,%s,%s)",
            (client, client, []),
        )
        yield {
            "grant_type": "client_credentials",
            "client_id": client,
            "client_secret": secret,
        }


def remove_client_secret(vault: VaultClient, path: str) -> None:
    """Удаляет все версии временного секрета и при потере ответа на запись. Отсутствующий ключ уже очищен."""
    try:
        vault.delete_secret_metadata(path)
    except httpx.HTTPStatusError as error:
        if error.response.status_code != httpx.codes.NOT_FOUND:
            raise
