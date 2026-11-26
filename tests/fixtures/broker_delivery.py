"""Проверки права чтения на штатном экземпляре с прерываемым AMQP-каналом."""

import time
from typing import Any

import pytest

from assertions.decisions import assert_decision
from parameters.auth_service import decisions as actions
from parameters.auth_service.decision_history import CompletedRead
from src.common import fields
from src.models.decision import Actor, decision_request
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.service_log import POLL_SECONDS, ServiceLog


def check_read(
    client: DecisionClient, actor: Actor, shared: str, case: CompletedRead
) -> dict[str, Any]:
    """Проверяет право чтения пространства на запросе с собственным request_id."""
    body = decision_request(actor, actions.READ, fields.ResourceType.SPACE, shared)
    return assert_decision(
        client.check_single_action(actor, body), body, case.allowed, case.reason
    )


def wait_for_disconnect(
    client: DecisionClient, actor: Actor, shared: str, log: ServiceLog
) -> None:
    """Дожидается обнаружения обрыва AMQP клиентом на отдельном пробном запросе."""
    deadline = time.monotonic() + 10
    attempts: set[str] = set()
    while time.monotonic() < deadline:
        body = decision_request(actor, actions.READ, fields.ResourceType.SPACE, shared)
        client.check_single_action(actor, body).raise_for_status()
        attempts.add(body[fields.REQUEST_ID_FIELD])
        if any(
            "decision audit delivery failed" in line
            and any(key in line for key in attempts)
            for line in log.read().splitlines()
        ):
            return
        time.sleep(POLL_SECONDS)
    pytest.fail("Нет подтверждения разрыва AMQP в изолированном экземпляре")
