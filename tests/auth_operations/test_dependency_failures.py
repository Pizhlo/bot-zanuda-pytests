"""Отказы зависимостей в процессе, который обслуживает только этот тест."""

import httpx
import pytest

from assertions.decision_failures import assert_failure_audit
from parameters.auth_service.decision_faults import DEPENDENCY_FAILURES, Fault
from src.common import fields
from src.models.decision import Actor, Role
from src.models.space import SpaceType
from src.storages.postgres_client import PostgresClient
from tests.fixtures.decision_outage import exercise_fault, fault_request
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.rabbitmq import AuditStream


@pytest.mark.parametrize(
    "fault", DEPENDENCY_FAILURES, ids=lambda fault: fault.dependency
)
def test_dependency_failure(  # noqa: WPS211 — подготовка личности, пространства и независимых наблюдателей отказа
    fault: Fault,
    decisions: DecisionClient,
    model_id: str,
    actors: dict[Role, Actor],
    spaces: dict[str, str],
    postgres_client: PostgresClient,
    audit_stream: AuditStream,
) -> None:
    """Проверяет, как сервис сообщает об отказе при поиске пользователя, проверке отношений и сохранении решения.

    Сбой PostgreSQL или OpenFGA приводит к 503 Service Unavailable без новой записи в истории. Аудит указывает
    этап отказа. Если сорвалась запись уже вычисленного решения, событие также содержит его результат и версии
    модели и политики как для разрешения, так и для отказа.
    """
    owner = (
        actors[Role.OUTSIDER]
        if fault.scenario in ("deny", SpaceType.PERSONAL)
        else actors[Role.OWNER]
    )
    body = fault_request(fault, owner, spaces)
    response = exercise_fault(decisions, postgres_client, fault, owner, body)
    request_id = body[fields.REQUEST_ID_FIELD]
    assert response.status_code == httpx.codes.SERVICE_UNAVAILABLE
    assert response.json() == {
        "error_code": fault.code,
        "message": fault.message,
        "request_id": request_id,
    }
    assert response.headers["X-Request-ID"] == request_id
    assert_failure_audit(audit_stream(), fault, request_id, model_id)
    assert not postgres_client.fetch_all(
        "SELECT 1 FROM auth.decisions WHERE request_id = %s", (request_id,)
    )
