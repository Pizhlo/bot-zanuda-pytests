"""Проекция заметки в PostgreSQL и граф её прав для проверки побочных эффектов решения."""

from collections.abc import Iterator
from contextlib import ExitStack
from uuid import uuid4

import httpx
import pytest

from src.models.decision import Actor, Role
from src.models.space import SpaceType
from src.storages.postgres_client import PostgresClient
from tests.fixtures.decisions import relation, seeded_relations


@pytest.fixture()
def stored_note(
    postgres_client: PostgresClient, openfga: httpx.Client, actors: dict[Role, Actor]
) -> Iterator[str]:
    """Создаёт собственные строки пространства и заметки и соответствующие им связи OpenFGA."""
    owner = actors[Role.OWNER]
    space, note = str(uuid4()), str(uuid4())
    keys = [
        relation("user:*", SpaceType.SHARED, f"space:{space}"),
        relation(f"user:{owner.user_id}", "owner", f"space:{space}"),
        relation(f"space:{space}", "space", f"note:{note}"),
        relation(f"user:{owner.user_id}", "owner", f"note:{note}"),
    ]
    with ExitStack() as cleanup:
        with postgres_client.raw_connection.transaction():
            postgres_client.execute(
                "INSERT INTO spaces.spaces(id,type,owner_id,default_participant_role) VALUES (%s,'SHARED',%s,'EDITOR')",
                (space, owner.user_id),
            )
            cleanup.callback(
                postgres_client.execute,
                "DELETE FROM spaces.spaces WHERE id = %s",
                (space,),
            )
            postgres_client.execute(
                "INSERT INTO notes.notes(id, space_id, author_id) VALUES (%s,%s,%s)",
                (note, space, owner.user_id),
            )
            cleanup.callback(
                postgres_client.execute,
                "DELETE FROM notes.notes WHERE id = %s",
                (note,),
            )
        cleanup.enter_context(seeded_relations(openfga, keys))
        yield note
