"""Проверки ответа и аудита конфликта синхронизации пространства."""

import json
from typing import Any

import httpx

from assertions.decisions import assert_decision
from parameters.auth_service import decisions as decision_params
from src.common import audit, fields
from src.models.decision import Actor, DecisionReasonCode, decision_request
from src.models.space import SpaceType
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.rabbitmq import QueueMessage


def assert_space_conflict(
    response: httpx.Response, delivery: QueueMessage, *, same_space_id: bool = False
) -> None:
    """Сверяет отказ с UUID именно проигравшего запроса, в том числе при конкурентной записи."""
    assert response.status_code == httpx.codes.CONFLICT, response.text
    request = json.loads(response.request.content)
    error = response.json()
    request_id = request[fields.REQUEST_ID_FIELD]
    assert error[fields.REQUEST_ID_FIELD] == request_id
    assert (
        error["error"]["code"] == audit.ErrorCode.RESOURCE_ALREADY_EXISTS_OR_NOT_FOUND
    )

    with delivery as message:
        assert message is not None
        event = audit.AuditMessage.model_validate_json(message)
        assert_conflict_event(event, request)
        assert_conflict_cause(event, error["error"]["message"], same_space_id)


def assert_conflict_event(event: audit.AuditMessage, request: dict[str, Any]) -> None:
    """Сопоставляет событие конфликта с исходным запросом, его операцией и пользователем."""
    expected = {
        fields.REQUEST_ID_FIELD: request[fields.REQUEST_ID_FIELD],
        "service_name": audit.AUTH_SERVICE_NAME,
        "operation": audit.Operation.FGA_UPDATE_RESOURCE,
        "status": audit.Status.FAILED,
        "kind": audit.Kind.VALIDATION,
    }
    assert event.model_dump(include=set(expected)) == expected
    assert (
        event.context
        and event.context[fields.USER_ID_FIELD] == request["relations"]["owner"]["id"]
    )


def assert_conflict_cause(
    event: audit.AuditMessage, detail: str, same_space_id: bool
) -> None:
    """Учитывает, успел ли второй запрос увидеть уже записанный UUID до вызова OpenFGA Write."""
    assert event.context and event.cause
    observed = (
        event.context[audit.STAGE_FIELD],
        event.error_code,
        event.level,
        event.message,
    )
    if detail.startswith("guard space invariants: "):
        assert same_space_id
        assert event.cause == detail.removeprefix("guard space invariants: ")
        assert observed == (
            "check_space_privacy",
            "VALIDATION_FAILED",
            audit.Level.DEBUG,
            "Space privacy constraint rejected the update",
        )
    else:
        assert observed == (
            "write_tuples",
            audit.ErrorCode.WRITE_FAILED_DUE_TO_INVALID_INPUT,
            audit.Level.ERROR,
            "OpenFGA rejected the tuple changes",
        )


def assert_personal_slot(
    actor: Actor, decisions: DecisionClient, space_id: str, available: bool
) -> None:
    """Проверяет через decisions/check право пользователя создать ещё одно личное пространство.
    Сверяет причину, чтобы отличить занятую личную отметку от общего отказа в доступе.
    """
    body = decision_request(
        actor,
        fields.Operation.CREATE,
        fields.ResourceType.SPACE,
        space_id,
        resource_attributes={fields.SPACE_TYPE_FIELD: SpaceType.PERSONAL},
    )
    reason = (
        DecisionReasonCode.FIRST_PERSONAL_SPACE
        if available
        else DecisionReasonCode.PERSONAL_SPACE_ALREADY_EXISTS
    )
    assert_decision(decisions.check_single_action(actor, body), body, available, reason)


def assert_space_read(
    actor: Actor, decisions: DecisionClient, space_id: str, allowed: bool
) -> None:
    """Запрашивает чтение кандидата после записи и проверяет сохранённое право владельца."""
    body = decision_request(
        actor, decision_params.READ, fields.ResourceType.SPACE, space_id
    )
    reason = (
        DecisionReasonCode.ALLOWED_VIA_FGA_RELATION
        if allowed
        else DecisionReasonCode.DENIED_BY_FGA_RELATION
    )
    assert_decision(decisions.check_single_action(actor, body), body, allowed, reason)
