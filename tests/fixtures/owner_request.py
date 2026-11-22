"""Запрос владельца на чтение shared для проверок идентификации."""

from typing import Any
from uuid import UUID

import pytest

from parameters.auth_service import decisions as decision_params
from src.common import fields
from src.models import decision
from src.models import space as space_model
from tests.fixtures.decisions import DecisionClient


@pytest.fixture()
def owner_request(
    actors: dict[decision.Role, decision.Actor],
    spaces: dict[str, str],
    decisions: DecisionClient,
) -> tuple[decision.Actor, dict[str, Any]]:
    """Готовит чтение общего пространства и регистрирует UUID запроса для очистки истории."""
    actor = actors[decision.Role.OWNER]
    body = decision.decision_request(
        actor,
        decision_params.READ,
        fields.ResourceType.SPACE,
        spaces[space_model.SpaceType.SHARED],
    )
    decisions.request_ids.add(UUID(body[fields.REQUEST_ID_FIELD]))
    return actor, body


type OwnerRequest = tuple[decision.Actor, dict[str, Any]]
