"""Управляемый отказ одной зависимости тестового процесса."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import httpx

from parameters.auth_service.decision_faults import Fault
from src.common import fields
from src.models import decision, space
from src.storages.postgres_client import PostgresClient
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.fault_proxy import disconnected


def exercise_fault(
    decisions: DecisionClient,
    postgres: PostgresClient,
    fault: Fault,
    owner: decision.Actor,
    body: dict[str, Any],
) -> httpx.Response:
    """После готовности изолированного процесса отключает только выбранную зависимость."""
    lock = (
        disconnected("openfga")
        if fault.dependency == "openfga"
        else block_query(postgres, fault.dependency == "identity")
    )
    with lock:
        return decisions.check_single_action(owner, body)


@contextmanager
def block_query(postgres: PostgresClient, identity: bool) -> Iterator[None]:
    """Удерживает транзакционную блокировку только в выделенном стенде до получения HTTP-ответа."""
    statement = (
        "LOCK TABLE users.telegram IN ACCESS EXCLUSIVE MODE"
        if identity
        else "LOCK TABLE auth.decisions IN SHARE MODE"
    )
    with postgres.raw_connection.transaction():
        postgres.execute(statement)
        yield


type Payload = dict[str, Any]


def fault_request(
    fault: Fault, actor: decision.Actor, spaces: dict[str, str]
) -> Payload:
    """Выбирает запрос, который должен дойти до проверяемой зависимости."""
    if fault.scenario in tuple(space.SpaceType):
        return decision.decision_request(
            actor,
            fields.Operation.CREATE,
            fields.ResourceType.SPACE,
            str(uuid4()),
            resource_attributes={fields.SPACE_TYPE_FIELD: fault.scenario},
        )
    return decision.decision_request(
        actor,
        fields.Operation.UPDATE,
        fields.ResourceType.SPACE,
        spaces[space.SpaceType.SHARED],
        action_attributes={fields.FIELD_MASK_FIELD: [fields.NAME_FIELD]},
    )
