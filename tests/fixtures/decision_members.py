"""Граф с двумя разными администраторами одного пространства."""

from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest

from src.models.decision import Actor, Role
from src.models.space import SpaceType
from tests.fixtures.decisions import relation, seeded_relations


@pytest.fixture(scope="module")
def peer_admin_space(openfga: httpx.Client, actors: dict[Role, Actor]) -> Iterator[str]:
    """Создаёт общее пространство с двумя администраторами с разными UUID.
    В графе второму пользователю назначается admin независимо от его роли в основной матрице.
    """
    space_id = str(uuid4())
    space = f"space:{space_id}"
    keys = [
        relation("user:*", SpaceType.SHARED, space),
        relation(f"user:{actors[Role.OWNER].user_id}", "owner", space),
    ]
    keys.extend(
        relation(f"user:{actors[role].user_id}", "admin", space)
        for role in (Role.ADMIN, Role.EDITOR)
    )
    with seeded_relations(openfga, keys):
        yield space_id
