"""Временные зарегистрированные пользователи тестового auth-service."""

from collections.abc import Iterator
from contextlib import ExitStack, closing, contextmanager
from uuid import UUID, uuid4

import pytest

from src.config import config
from src.models.decision import Actor, Role
from src.storages.postgres_client import PostgresClient
from tests.fixtures.telegram import new_telegram_id


def new_actor() -> Actor:
    """Выделяет пару тестовых идентификаторов до создания записей в PostgreSQL."""
    return Actor(str(uuid4()), new_telegram_id())


@contextmanager
def registered_actors(roles: tuple[Role, ...]) -> Iterator[dict[Role, Actor]]:
    """Регистрирует временные личности в БД сервиса и удаляет их по собственным UUID."""
    identities = {role: new_actor() for role in roles}
    with ExitStack() as cleanup:
        db = cleanup.enter_context(
            closing(PostgresClient.connect(config.postgres, autocommit=True))
        )
        ids = [UUID(actor.user_id) for actor in identities.values()]
        cleanup.callback(
            db.execute,
            "DELETE FROM users.users WHERE id = ANY(%s)",
            (ids,),
        )
        with db.raw_connection.transaction():
            for actor in identities.values():
                db.execute("INSERT INTO users.users(id) VALUES (%s)", (actor.user_id,))
                db.execute(
                    "INSERT INTO users.telegram(id, tg_id, user_id, global_invite_policy) "
                    "VALUES (%s, %s, %s, 'ALLOW_ALL')",
                    (uuid4(), int(actor.telegram_id), actor.user_id),
                )
        yield identities


@pytest.fixture(scope="session")
def actors() -> Iterator[dict[Role, Actor]]:
    """Предоставляет независимые личности для чтения общей матрицы прав."""
    with registered_actors(tuple(Role)) as identities:
        yield identities
