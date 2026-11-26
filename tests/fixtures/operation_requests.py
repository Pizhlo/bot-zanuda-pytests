"""Запросы для проверки фактического объекта решения и доверенного контекста."""

from typing import Any
from uuid import uuid4

from assertions.decisions import assert_decision
from parameters.auth_service import decisions as actions
from parameters.auth_service.decision_history import Operation
from parameters.auth_service.wire_decisions import PRIVATE_VALUE
from src.common import fields
from src.models.decision import Actor, DecisionReasonCode, Role, decision_request
from src.models.space import SpaceType
from tests.fixtures.decisions import DecisionClient


def operation_request(
    case: Operation, actors: dict[Role, Actor], parent: str
) -> dict[str, Any]:
    """Добавляет поля для конкретной операции и заведомо недоверенные подсказки контекста."""
    target = str(uuid4())
    if case.kind == actions.MEMBER:
        target = actors[Role.VIEWER].user_id
    attrs: dict[str, Any] = (
        {fields.ROLE_FIELD: Role.EDITOR} if case.kind == actions.MEMBER else {}
    )
    resource: dict[str, str] = (
        {fields.SPACE_TYPE_FIELD: SpaceType.SHARED}
        if case.kind == fields.ResourceType.SPACE
        else {fields.SPACE_ID_FIELD: parent}
    )
    if case.action == fields.Operation.UPDATE:
        target = parent
        resource = {}
        attrs = {fields.FIELD_MASK_FIELD: [fields.NAME_FIELD]}
    body = decision_request(
        actors[Role.OWNER],
        case.action,
        case.kind,
        target,
        action_attributes=attrs,
        resource_attributes=resource,
    )
    body["context"] = {
        "service": PRIVATE_VALUE,
        "client": PRIVATE_VALUE,
        "time": "2001-01-01T00:00:00Z",
        "ip": "192.0.2.1",
    }
    return body


def send_operation(
    decisions: DecisionClient, owner: Actor, body: dict[str, Any], case: Operation
) -> dict[str, Any]:
    """Проверяет решение и объяснение относительно фактически выполненной операции."""
    response = decisions.check_single_action(owner, body)
    reasons = [case.reason]
    if case.action == fields.Operation.UPDATE:
        reasons.append(DecisionReasonCode.ALLOWED_FIELDS)
    decision = assert_decision(response, body, True, *reasons)
    assert decisions.token not in response.text and PRIVATE_VALUE not in response.text
    if case.relation:
        resource = body[fields.RESOURCE_FIELD]
        parent = resource["attributes"].get(fields.SPACE_ID_FIELD) or resource["id"]
        assert (
            decision["reasons"][0]["message"]
            == f'OpenFGA allowed relation "{case.relation}" on space:{parent} for user:{owner.user_id}'
        )
    return decision
