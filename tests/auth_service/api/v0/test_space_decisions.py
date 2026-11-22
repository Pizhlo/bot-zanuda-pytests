"""Решения для пространств, включая неполную и противоречивую классификацию."""

from uuid import uuid4

import pytest

from assertions.decision_fields import assert_mask
from assertions.decisions import assert_decision
from parameters.auth_service import space_decisions as cases
from src.common import fields
from src.models.decision import Actor, DecisionReasonCode, Role, decision_request
from src.models.space import SpaceType
from tests.fixtures.decisions import DecisionClient


@pytest.mark.parametrize("role", Role)
@pytest.mark.parametrize(("kind", "action", "allowed_roles"), cases.SPACE_ACCESS_CASES)
def test_existing_space(  # noqa: WPS211,WPS210 — сценарий и отдельные фикстуры стенда
    actors: dict[Role, Actor],
    spaces: dict[str, str],
    decisions: DecisionClient,
    kind: str,
    action: str,
    role: Role,
    allowed_roles: tuple[Role, ...],
) -> None:
    """Проверяет чтение, переименование и удаление пространства от имени каждой роли.
    Права зависят от сохранённого типа. Для неизвестного объекта или графа
    с отсутствующей либо противоречивой отметкой типа ожидается отказ.
    """
    actor = actors[role]
    object_id = spaces.get(kind) or str(uuid4())
    attrs = (
        {fields.FIELD_MASK_FIELD: [fields.NAME_FIELD]}
        if action == fields.Operation.UPDATE
        else {}
    )
    body = decision_request(
        actor, action, fields.ResourceType.SPACE, object_id, action_attributes=attrs
    )
    allowed = role in allowed_roles
    codes = (
        (DecisionReasonCode.ALLOWED_VIA_FGA_RELATION, DecisionReasonCode.ALLOWED_FIELDS)
        if action == fields.Operation.UPDATE
        else (DecisionReasonCode.ALLOWED_VIA_FGA_RELATION,)
    )
    assert_decision(
        decisions.check_single_action(actor, body),
        body,
        allowed,
        *(codes if allowed else (DecisionReasonCode.DENIED_BY_FGA_RELATION,)),
    )


@pytest.mark.usefixtures("spaces")
@pytest.mark.parametrize("creation", cases.SPACE_CREATION_CASES, ids=str)
def test_create_space(
    actors: dict[Role, Actor],
    decisions: DecisionClient,
    creation: cases.SpaceCreation,
) -> None:
    """Проверяет право зарегистрированного пользователя создать общее или личное пространство.

    Общее пространство может создать пользователь с любой ролью. Создание личного пространства
    разрешается только при отсутствии у пользователя отметки о ранее созданном личном пространстве.
    """
    actor = actors[creation.role]
    body = decision_request(
        actor,
        fields.Operation.CREATE,
        fields.ResourceType.SPACE,
        str(uuid4()),
        resource_attributes={fields.SPACE_TYPE_FIELD: creation.kind},
    )
    assert_decision(
        decisions.check_single_action(actor, body),
        body,
        creation.allowed,
        creation.reason,
    )


@pytest.mark.parametrize(("mask", "allowed"), cases.SPACE_FIELD_CASES)
@pytest.mark.parametrize("kind", [SpaceType.SHARED, SpaceType.PERSONAL])
def test_space_field_policy(  # noqa: WPS211 — матрица масок на двух типах пространства
    actors: dict[Role, Actor],
    spaces: dict[str, str],
    decisions: DecisionClient,
    kind: SpaceType,
    mask: list[str],
    allowed: bool,
) -> None:
    """Проверяет, какие поля владелец может изменить у общего и личного пространства.

    Владелец может переименовать пространство, даже если имя указано в маске дважды. При попытке
    изменить защищённое или неизвестное поле сервис отклоняет всю маску и перечисляет запрещённые поля.
    """
    actor = actors[Role.OWNER]
    body = decision_request(
        actor,
        fields.Operation.UPDATE,
        fields.ResourceType.SPACE,
        spaces[kind],
        action_attributes={fields.FIELD_MASK_FIELD: mask},
    )
    forbidden = [] if allowed else [name for name in mask if name != fields.NAME_FIELD]
    assert_mask(decisions.check_single_action(actor, body), body, mask, forbidden)
