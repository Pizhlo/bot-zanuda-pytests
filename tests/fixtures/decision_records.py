"""Записи с собственным автором и существующими, отсутствующими или конфликтующими родителями."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
import pytest

from parameters.auth_service.record_decisions import RecordCase
from src.common import fields
from src.models.decision import Actor, Role, decision_request
from src.models.space import SpaceType
from tests.fixtures.decisions import relation, seeded_relations


@dataclass(frozen=True)
class Records:
    """Хранит UUID записей для сочетаний родителя и автора в графе текущего типа ресурса."""

    kind: str
    spaces: dict[str, str]
    ids: dict[tuple[str, Role], str]

    def request(self, case: RecordCase, actor: Actor) -> dict[str, Any]:
        """Подставляет чужой space_id, чтобы проверить доступ по сохранённому родителю."""
        claimed = self.spaces[
            SpaceType.PERSONAL if case.space == SpaceType.SHARED else SpaceType.SHARED
        ]
        return decision_request(
            actor,
            case.action,
            self.kind,
            self.ids[case.space, case.author],
            action_attributes={fields.FIELD_MASK_FIELD: [fields.TITLE_FIELD]}
            if case.action == fields.Operation.UPDATE
            else {},
            resource_attributes={fields.SPACE_ID_FIELD: claimed},
        )


@pytest.fixture(scope="module")
def records(  # noqa: WPS210 — построение графа записей для одного типа
    request: pytest.FixtureRequest,
    openfga: httpx.Client,
    actors: dict[Role, Actor],
    spaces: dict[str, str],
) -> Iterator[Records]:
    """Создаёт для запрошенного типа записи с разными авторами и родителями.
    Неизвестный UUID остаётся без связей. Для осиротевшей записи сохраняется автор,
    а для неоднозначной задаются две связи space. После модуля граф удаляется.
    """
    kind: str = request.param
    other_personal = f"space:{uuid4()}"
    record_ids = {}
    keys = [
        relation("user:*", SpaceType.PERSONAL, other_personal),
        relation(f"user:{actors[Role.ADMIN].user_id}", "owner", other_personal),
    ]
    for parent in (*spaces, "orphan", "unknown", "two_parents"):
        authors = (
            tuple(Role)
            if parent in (SpaceType.SHARED, SpaceType.PERSONAL)
            else (Role.VIEWER,)
        )
        for author in authors:
            record_id = str(uuid4())
            record_ids[parent, author] = record_id
            if parent != "unknown":
                keys.extend(
                    record_relations(kind, record_id, actors[author], parent, spaces)
                )
    record_id = str(uuid4())
    record_ids["different_owners", Role.VIEWER] = record_id
    keys.extend(
        record_relations(kind, record_id, actors[Role.VIEWER], SpaceType.SHARED, spaces)
    )
    keys.append(relation(other_personal, fields.Relation.SPACE, f"{kind}:{record_id}"))

    with seeded_relations(openfga, keys):
        yield Records(kind, spaces, record_ids)


def record_relations(
    kind: str,
    record_id: str,
    author: Actor,
    parent: str,
    spaces: dict[str, str],
) -> list[dict[str, str]]:
    """Формирует связи сохранённой записи с её автором и родителями.
    Осиротевшая запись получает только owner, запись с двумя родителями получает обе связи space.
    """
    resource = f"{kind}:{record_id}"
    keys = [relation(f"user:{author.user_id}", "owner", resource)]
    parents = (
        (SpaceType.SHARED, SpaceType.PERSONAL) if parent == "two_parents" else (parent,)
    )
    keys.extend(
        relation(f"space:{spaces[name]}", fields.Relation.SPACE, resource)
        for name in parents
        if name in spaces
    )
    return keys
