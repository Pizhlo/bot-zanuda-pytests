"""Изолированные участники и граф отношений для публичного decisions/check."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common import fields
from src.models import decision, space as space_model
from src.storages.postgres_client import PostgresClient
from tests.fixtures.openfga import remove_resource_relations

SPACE_KINDS = (
    space_model.SpaceType.SHARED,
    space_model.SpaceType.PERSONAL,
    "untyped",
    "conflicting",
)


def relation(subject: str, name: str, resource: str) -> dict[str, str]:
    """Описывает тройку OpenFGA в формате API записи для тестового графа."""
    return {"user": subject, "relation": name, "object": resource}


@contextmanager
def seeded_relations(
    client: httpx.Client, keys: list[dict[str, str]]
) -> Iterator[None]:
    """Записывает связи уникальных тестовых объектов в OpenFGA на время сценария.
    Регистрирует очистку каждого объекта до отправки записи, поскольку сервер
    может сохранить связи и потерять HTTP-ответ. Ошибка одной уборки не отменяет остальные.
    """
    with ExitStack() as cleanup:
        owned_objects = {key["object"] for key in keys}
        for object_ref in owned_objects:
            cleanup.callback(remove_resource_relations, client, object_ref)
        response = client.post("write", json={"writes": {"tuple_keys": keys}})
        response.raise_for_status()
        yield


@pytest.fixture(scope="session")
def spaces(  # noqa: WPS210 — перечисление связей тестовых пространств
    openfga: httpx.Client, actors: dict[decision.Role, decision.Actor]
) -> Iterator[dict[str, str]]:
    """Создаёт общий граф для проверок прав без изменения членства между тестами.
    Для personal, shared и повреждённых пространств задаются одинаковые роли,
    чтобы различие в решениях отражало именно тип пространства.
    """
    graph = {kind: str(uuid4()) for kind in SPACE_KINDS}
    owner = f"user:{actors[decision.Role.OWNER].user_id}"
    keys = [relation(owner, "has_personal_space", owner)]
    for kind, space_id in graph.items():
        space = f"space:{space_id}"
        keys.extend(
            relation(f"user:{actor.user_id}", role, space)
            for role, actor in actors.items()
            if role != decision.Role.OUTSIDER
        )
        markers = (
            (space_model.SpaceType.PERSONAL, space_model.SpaceType.SHARED)
            if kind == "conflicting"
            else (kind,)
        )
        keys.extend(
            relation("user:*", marker, space)
            for marker in markers
            if marker != "untyped"
        )
    with seeded_relations(openfga, keys):
        yield graph


def new_request_header_id(request_ids: set[UUID]) -> str:
    """Выделяет X-Request-ID и заранее регистрирует его для очистки истории после теста."""
    header_id = uuid4()
    request_ids.add(header_id)
    return str(header_id)


@dataclass
class DecisionClient:
    """Отправляет запрос с доверенным заголовком и регистрирует UUID до HTTP-вызова."""

    api: AuthServiceV0APIClient
    token: str
    request_ids: set[UUID]

    def check_single_action(
        self, actor: decision.Actor, body: dict[str, Any]
    ) -> httpx.Response:
        """Проверяет одно действие через decisions/check с Telegram ID инициатора и сохраняет request_id для очистки."""
        self.request_ids.add(UUID(body[fields.REQUEST_ID_FIELD]))
        return self.api.check_decision(self.token, actor.telegram_id, body)


@pytest.fixture()
def decision_request_ids(postgres_client: PostgresClient) -> Iterator[set[UUID]]:
    """Регистрирует UUID до HTTP-вызова и удаляет возможные записи после сценария."""
    request_ids: set[UUID] = set()
    try:
        yield request_ids
    finally:
        postgres_client.execute(
            "DELETE FROM auth.decisions WHERE request_id = ANY(%s)",
            (list(request_ids),),
        )


@pytest.fixture()
def decisions(
    auth_service_v0_api_client: AuthServiceV0APIClient,
    login: str,
    decision_request_ids: set[UUID],
) -> DecisionClient:
    """Предоставляет клиент с токеном тестового бота и учётом request_id текущего теста.
    Идентификатор регистрируется до отправки, чтобы возможную запись можно было удалить
    и после сетевой ошибки или неуспешной проверки ответа.
    """
    return DecisionClient(auth_service_v0_api_client, login, decision_request_ids)
