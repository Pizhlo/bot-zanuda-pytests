"""Доверенная личность, повтор запроса и сохранение решений."""

from contextlib import AbstractContextManager
from uuid import uuid4

import httpx
import pytest

from assertions.decisions import (
    assert_decision,
    assert_failed_decision,
    assert_saved_reads,
)
from parameters.auth_service import decisions as decision_params
from src.common import fields
from src.models.decision import Actor, Role, decision_request
from src.models.space import SpaceType
from src.storages.postgres_client import PostgresClient
from tests.fixtures.decisions import DecisionClient


@pytest.mark.parametrize(
    ("role", "allowed", "expected"), decision_params.REPEATED_READ_CASES
)
def test_repeated_decision(  # noqa: WPS211 — ожидание кейса и независимые фикстуры
    role: Role,
    allowed: bool,
    expected: dict[str, object],
    actors: dict[Role, Actor],
    spaces: dict[str, str],
    decisions: DecisionClient,
    postgres_client: PostgresClient,
) -> None:
    """Проверяет повторный запрос на чтение общего пространства с тем же request_id.

    Владелец получает разрешение при обеих попытках, посторонний пользователь получает отказ.
    У каждого ответа свой decision_id, и в истории сохраняются оба результата.
    """
    actor = actors[role]
    space_id = spaces[SpaceType.SHARED]
    body = decision_request(
        actor, decision_params.READ, fields.ResourceType.SPACE, space_id
    )
    body.pop(fields.OPTIONS_FIELD)

    first = assert_decision(decisions.check_single_action(actor, body), body, allowed)
    second = assert_decision(decisions.check_single_action(actor, body), body, allowed)
    assert first[fields.DECISION_ID_FIELD] != second[fields.DECISION_ID_FIELD]

    assert_saved_reads(postgres_client, body, expected, (first, second))


def test_subject_mismatch(
    actors: dict[Role, Actor],
    decisions: DecisionClient,
    auth_service_error_messages_from_rabbitmq: AbstractContextManager[bytes | None],
    postgres_client: PostgresClient,
) -> None:
    """Проверяет, что зритель не может получить решение от имени владельца, указав его UUID в теле запроса.

    Сервис возвращает 403 Forbidden с причиной subject_mismatch. Ответ и событие RabbitMQ содержат
    идентификатор отклонённого запроса, а в истории решений запись не появляется.
    """
    body = decision_request(
        actors[Role.OWNER],
        decision_params.READ,
        fields.ResourceType.SPACE,
        str(uuid4()),
    )
    response = decisions.check_single_action(actors[Role.VIEWER], body)
    with auth_service_error_messages_from_rabbitmq as message:
        assert_failed_decision(
            message,
            response,
            body[fields.REQUEST_ID_FIELD],
            code="subject_mismatch",
            stage="verify_subject",
        )
    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json()["error_code"] == "subject_mismatch"
    assert response.json()[fields.REQUEST_ID_FIELD] == body[fields.REQUEST_ID_FIELD]
    assert not postgres_client.fetch_all(
        "SELECT 1 FROM auth.decisions WHERE request_id = %s",
        (body[fields.REQUEST_ID_FIELD],),
    )
