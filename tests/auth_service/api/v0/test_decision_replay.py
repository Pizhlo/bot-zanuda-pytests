"""Повторный запрос после отзыва роли в OpenFGA."""

from typing import Any
from uuid import uuid4

import httpx

from assertions.decision_log import assert_logged_replay
from parameters.auth_service import decisions as actions
from src.common import fields
from src.models.decision import Actor, Role, decision_request
from src.storages.postgres_client import PostgresClient
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.service_log import ServiceLog
from tests.fixtures.viewer_grant import read_before_and_after_revocation


def test_replay_after_revocation(
    decisions: DecisionClient,
    actors: dict[Role, Actor],
    postgres_client: PostgresClient,
    openfga: httpx.Client,
    service_log: ServiceLog | None,
) -> None:
    """Проверяет повторную проверку доступа к общему пространству после отзыва роли зрителя.

    В режиме higher_consistency тот же request_id даёт разрешение до отзыва и отказ после него. Обе попытки
    имеют разные decision_id, сохраняются в истории и каждую можно сопоставить с её локальным событием аудита.
    """
    body = decision_request(
        actors[Role.VIEWER], actions.READ, fields.ResourceType.SPACE, str(uuid4())
    )
    first, second = read_before_and_after_revocation(
        decisions, openfga, actors[Role.VIEWER], body
    )
    if service_log is not None:
        assert_logged_replay(service_log, (first, second), decisions.token)
    assert_revoked_result(body, second)
    assert_attempt_ids(postgres_client, first, second)


def assert_revoked_result(body: dict[str, Any], second: dict[str, Any]) -> None:
    """Сверяет текст отказа с ролью, отозванной между двумя попытками."""
    resource = "space:{id}".format_map(body[fields.RESOURCE_FIELD])
    subject = "user:{id}".format_map(body[fields.SUBJECT_FIELD])
    assert (
        second["reasons"][0]["message"]
        == f'OpenFGA denied relation "can_view" on {resource} for {subject}'
    )


def assert_attempt_ids(
    postgres_client: PostgresClient, first: dict[str, Any], second: dict[str, Any]
) -> None:
    """Проверяет, что история содержит ровно две попытки с этим request_id."""
    assert first[fields.DECISION_ID_FIELD] != second[fields.DECISION_ID_FIELD]
    rows = postgres_client.fetch_all(
        "SELECT decision_id, result FROM auth.decisions WHERE request_id = %s",
        (first[fields.REQUEST_ID_FIELD],),
    )
    stored = {str(row[fields.DECISION_ID_FIELD]): row["result"] for row in rows}
    assert stored == {
        first[fields.DECISION_ID_FIELD]: first["result"],
        second[fields.DECISION_ID_FIELD]: second["result"],
    }
