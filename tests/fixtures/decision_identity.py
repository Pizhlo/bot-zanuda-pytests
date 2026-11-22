"""Временный сервисный клиент с явно выданными scopes и подписанными JWT для decisions/check."""

import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from functools import partial
from uuid import uuid4

import pytest

from parameters.auth_service.decision_identity import TokenCase
from src.common import fields
from src.storages.postgres_client import PostgresClient
from tests.fixtures.auth_jwt import TokenFields

ISSUED_SECONDS_AGO = 120
TOKEN_TTL_SECONDS = 600


@pytest.fixture()
def scoped_token(
    postgres_client: PostgresClient, jwt_token_factory: Callable[..., str]
) -> Iterator[Callable[[TokenCase], str]]:
    """Регистрирует владельца scopes bot, admin и not-bot. Невыданный scope остаётся только в тестовом JWT."""
    client = str(uuid4())

    with ExitStack() as cleanup:
        cleanup.callback(
            postgres_client.execute,
            "DELETE FROM auth.service_clients WHERE client_id = %s",
            (client,),
        )
        postgres_client.execute(
            "INSERT INTO auth.service_clients(client_id, client_name, scopes) VALUES (%s, %s, %s)",
            (client, client, ["bot", "admin", "not-bot"]),
        )
        yield partial(issue, client, jwt_token_factory)


def issue(client: str, jwt_token_factory: Callable[..., str], case: TokenCase) -> str:
    """Подписывает токен этого клиента с нужным сроком действия."""
    if case.mode == "invalid":
        return "invalid.test.token"
    now = int(time.time())
    expiry = now - 1 if case.mode == "expired" else now + TOKEN_TTL_SECONDS
    claims = TokenFields(
        sub=client,
        aud=[fields.AUDIENCE_INTERNAL_API],
        iss=fields.ISSUER_AUTH_SERVICE,
        iat=now - ISSUED_SECONDS_AGO,
        exp=expiry,
        scope=case.scope,
    )
    return jwt_token_factory(token_fields=claims)
