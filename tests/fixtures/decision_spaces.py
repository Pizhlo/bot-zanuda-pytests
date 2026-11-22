"""Изолированные авторы и кандидаты на создание пространства."""

from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from uuid import uuid4

import httpx
import pytest

from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common import fields
from src.models import decision, space as space_model
from tests.fixtures.decision_actors import registered_actors
from tests.fixtures.openfga import remove_resource_relations


@dataclass
class SpaceWriter:
    """Отправляет синхронизацию для двух UUID и пользователей, принадлежащих одному тесту."""

    api: AuthServiceV0APIClient
    token: str
    actors: dict[decision.Role, decision.Actor]
    # Обе попытки записи принадлежат одному тесту.
    object_ids: tuple[str, str]

    def create(
        self, actor: decision.Actor, space_id: str, kind: space_model.SpaceType
    ) -> httpx.Response:
        """Отправляет resources/update с новым ключом идемпотентности для данной попытки записи."""
        body = {
            fields.REQUEST_ID_FIELD: str(uuid4()),
            fields.DECISION_ID_FIELD: str(uuid4()),
            "idempotency_key": str(uuid4()),
            fields.RESOURCE_FIELD: {
                fields.TYPE_FIELD: fields.ResourceType.SPACE,
                fields.ID_FIELD: space_id,
                fields.ATTRIBUTES_FIELD: {fields.SPACE_TYPE_FIELD: kind},
            },
            "relations": {
                "owner": {
                    fields.TYPE_FIELD: "user",
                    fields.ID_FIELD: actor.user_id,
                }
            },
            "operation": fields.Operation.CREATE,
            "change_type": "resource_added",
            "context": {
                "source_service": "pytests",
                "event_type": "SPACE_CREATED",
            },
        }
        return self.api.update_resource(
            body, token=self.token, x_telegram_user_id=actor.telegram_id
        )


@pytest.fixture()
def writer(
    openfga: httpx.Client,
    login: str,
    auth_service_v0_api_client: AuthServiceV0APIClient,
) -> Iterator[SpaceWriter]:
    """Убирает кандидатов и маркеры обоих инициаторов, даже если одна очистка упала."""
    object_ids = (str(uuid4()), str(uuid4()))
    with ExitStack() as cleanup:
        actors = cleanup.enter_context(
            registered_actors((decision.Role.EDITOR, decision.Role.OUTSIDER))
        )
        for actor in actors.values():
            cleanup.callback(
                remove_resource_relations, openfga, f"user:{actor.user_id}"
            )
        for resource_id in object_ids:
            cleanup.callback(remove_resource_relations, openfga, f"space:{resource_id}")
        yield SpaceWriter(auth_service_v0_api_client, login, actors, object_ids)
