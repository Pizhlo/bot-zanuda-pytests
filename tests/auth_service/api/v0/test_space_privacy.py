"""Запрет обхода правил пространства через прямую запись в resources/update."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import httpx
import pytest

from parameters.auth_service.space_privacy import PRIVACY_CASES, PrivacyCase
from src.common import audit, fields
from src.models.decision import Actor, Role
from src.models.space import SpaceType
from tests.fixtures.decision_spaces import SpaceWriter
from tests.fixtures.openfga import resource_tuple_keys
from tests.fixtures.rabbitmq import QueueMessage


def event_for(change: fields.ChangeType) -> tuple[fields.Operation, fields.EventType]:
    """Выбирает допустимую пару operation/event_type для синхронизации."""
    return {
        fields.ChangeType.MEMBERSHIP_ADDED: (
            fields.Operation.CREATE,
            fields.EventType.SPACE_CREATED,
        ),
        fields.ChangeType.MEMBERSHIP_REMOVED: (
            fields.Operation.DELETE,
            fields.EventType.SPACE_DELETED,
        ),
        fields.ChangeType.RESOURCE_ADDED: (
            fields.Operation.CREATE,
            fields.EventType.SPACE_CREATED,
        ),
        fields.ChangeType.RESOURCE_REMOVED: (
            fields.Operation.DELETE,
            fields.EventType.SPACE_DELETED,
        ),
    }.get(change, (fields.Operation.UPDATE, fields.EventType.SPACE_UPDATED))


type Relations = set[tuple[str, str]]


def privacy_request(
    case: PrivacyCase, space: str, owner: Actor, other: Actor
) -> dict[str, Any]:
    """Собирает валидное событие создания, удаления или изменения состава от имени владельца."""
    operation, event = event_for(case.change)
    relations: dict[str, Any] = {
        "owner": {
            "type": "user",
            fields.ID_FIELD: other.user_id if case.foreign_owner else owner.user_id,
        }
    }
    if case.change in (
        fields.ChangeType.MEMBERSHIP_ADDED,
        fields.ChangeType.MEMBERSHIP_CHANGED,
        fields.ChangeType.MEMBERSHIP_REMOVED,
    ):
        target = (
            owner
            if case.stored == SpaceType.SHARED and case.requested is None
            else other
        )
        relations["members"] = [
            {"user_id": target.user_id, "old_role": "viewer", "new_role": "editor"}
        ]
    attrs = {} if case.requested is None else {fields.SPACE_TYPE_FIELD: case.requested}
    return {
        "resource": {"type": "space", fields.ID_FIELD: space, "attributes": attrs},
        "relations": relations,
        "change_type": case.change,
        "operation": operation,
        "decision_id": str(uuid4()),
        "context": {"source_service": "pytests", "event_type": event},
    }


def graph_snapshot(
    openfga: httpx.Client, resources: tuple[str, ...]
) -> list[Relations]:
    """Читает владельца, тип и все остальные связи объектов независимо от порядка OpenFGA."""
    return [
        {
            (key["user"], key["relation"])
            for key in resource_tuple_keys(openfga, resource)
        }
        for resource in resources
    ]


def assert_privacy_failure(
    response: httpx.Response, body: dict[str, Any], delivery: QueueMessage
) -> None:
    """Сверяет код ошибки, идентификаторы запроса и ресурса, а также итоговое событие отказа."""
    assert response.status_code == httpx.codes.BAD_REQUEST, response.text
    error = response.json()
    assert (error["request_id"], error["status"], error["result"]) == (
        body["request_id"],
        "error",
        "failed",
    )
    assert error["resource"][fields.ID_FIELD] == body["resource"][fields.ID_FIELD]
    assert error["error"]["code"] == "VALIDATION_FAILED"
    assert_privacy_event(delivery, body["request_id"])


def assert_privacy_event(delivery: QueueMessage, request_id: str) -> None:
    """Проверяет, что событие в RabbitMQ связано с запросом и содержит этап проверки приватности и непустую причину отказа."""
    with delivery as raw:
        assert raw is not None
        event = audit.AuditMessage.model_validate_json(raw)
        assert (event.request_id, event.operation, event.status, event.error_code) == (
            request_id,
            audit.Operation.FGA_UPDATE_RESOURCE,
            audit.Status.FAILED,
            "VALIDATION_FAILED",
        )
        assert (
            event.context
            and event.context["stage"] == "check_space_privacy"
            and event.cause
        )


@pytest.mark.parametrize("case", PRIVACY_CASES)
def test_direct_space_write(
    case: PrivacyCase,
    privacy_writer: SpaceWriter,
    openfga: httpx.Client,
    audit_stream: Callable[[], QueueMessage],
) -> None:
    """Проверяет, что прямая синхронизация пространства не позволяет обойти ограничения его типа и состава.

    Некорректный тип, чужой владелец при создании и запрещённая операция над пространством или его участниками
    приводят к 400 Bad Request. Даже с новым ключом каждая попытка оставляет граф прежним и даёт событие отказа.
    """
    owner = privacy_writer.actors[Role.EDITOR]
    space = privacy_writer.object_ids[0]
    resources = (
        f"space:{space}",
        f"user:{owner.user_id}",
        f"user:{privacy_writer.actors[Role.OUTSIDER].user_id}",
    )
    initial = graph_snapshot(openfga, resources)
    body = privacy_request(case, space, owner, privacy_writer.actors[Role.OUTSIDER])
    for _ in range(2):
        send_rejected_write(privacy_writer, body.copy(), audit_stream())
        assert graph_snapshot(openfga, resources) == initial


def send_rejected_write(
    writer: SpaceWriter, body: dict[str, Any], delivery: QueueMessage
) -> None:
    """Выдаёт новой попытке собственные идентификаторы и сопоставляет ответ с сообщением аудита."""
    body.update(request_id=str(uuid4()), idempotency_key=str(uuid4()))
    owner = writer.actors[Role.EDITOR]
    response = writer.api.update_resource(
        body, token=writer.token, x_telegram_user_id=owner.telegram_id
    )
    assert_privacy_failure(response, body, delivery)
