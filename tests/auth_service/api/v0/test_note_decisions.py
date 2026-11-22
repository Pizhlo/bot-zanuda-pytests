"""Бизнес-правила для заметок во всех ролях и типах пространства."""

from uuid import uuid4

import pytest

from assertions.decisions import assert_decision
from assertions.decision_fields import assert_mask
from assertions.record_decisions import assert_record_access
from parameters.auth_service import record_decisions as cases
from src.common import fields
from src.models.decision import Actor, DecisionReasonCode, Role, decision_request
from src.models.space import SpaceType
from tests.fixtures.decision_records import Records
from tests.fixtures.decisions import DecisionClient

pytestmark = pytest.mark.parametrize(
    "records", [fields.ResourceType.NOTE], indirect=True, scope="module"
)


@pytest.mark.parametrize("case", cases.RECORD_ACCESS_CASES, ids=str)
def test_note_access(
    case: cases.RecordCase,
    actors: dict[Role, Actor],
    records: Records,
    decisions: DecisionClient,
) -> None:
    """Проверяет права на чтение, обновление и удаление заметки с учётом роли и авторства.

    В общем пространстве учитываются авторство и роль, в личном доступ имеет только владелец.
    Решение определяется сохранёнными связями, даже если запрос указывает другое пространство.
    Для неизвестной записи или записи без определённого родительского типа ожидается отказ.
    """
    actor = actors[case.actor]
    body = records.request(case, actor)
    response = decisions.check_single_action(actor, body)
    assert_record_access(response, body, case)


@pytest.mark.parametrize(("parent", "role", "allowed"), cases.RECORD_CREATION_CASES)
def test_create_note(  # noqa: WPS211 — родители, роли и фикстуры API
    parent: str,
    allowed: bool,
    role: Role,
    actors: dict[Role, Actor],
    records: Records,
    decisions: DecisionClient,
) -> None:
    """Проверяет, кто может создать заметку в указанном родительском пространстве.

    В общем пространстве это разрешено владельцу, администратору и редактору, в личном только владельцу.
    Неизвестный родитель или неоднозначный тип дают отказ. Объяснение указывает проверенное пространство.
    """
    actor = actors[role]
    parent_id = records.spaces.get(parent) or str(uuid4())
    body = decision_request(
        actor,
        fields.Operation.CREATE,
        records.kind,
        str(uuid4()),
        resource_attributes={fields.SPACE_ID_FIELD: parent_id},
    )

    response = decisions.check_single_action(actor, body)
    assert_decision(
        response,
        body,
        allowed,
        DecisionReasonCode.ALLOWED_VIA_FGA_RELATION
        if allowed
        else DecisionReasonCode.DENIED_BY_FGA_RELATION,
    )
    assert f"space:{parent_id}" in response.json()["reasons"][0]["message"]


@pytest.mark.parametrize(("mask", "forbidden"), cases.RECORD_FIELD_CASES)
def test_note_field_policy(
    mask: list[str],
    forbidden: list[str],
    actors: dict[Role, Actor],
    records: Records,
    decisions: DecisionClient,
) -> None:
    """Проверяет, какие поля заметки разрешено обновить пользователю с правом редактирования.

    Повтор редактируемого поля допустим. Служебное или неизвестное поле приводит к отказу для всей маски.
    В объяснении каждое запрещённое поле перечисляется один раз.
    """
    actor = actors[Role.OWNER]
    body = decision_request(
        actor,
        fields.Operation.UPDATE,
        records.kind,
        records.ids[SpaceType.SHARED, Role.OWNER],
        action_attributes={fields.FIELD_MASK_FIELD: mask},
    )
    response = decisions.check_single_action(actor, body)
    assert_mask(response, body, mask, forbidden)
