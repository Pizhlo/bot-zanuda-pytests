"""Граница публичного JSON-контракта после аутентификации."""

import json
import uuid
from typing import Any

import httpx
import pytest

from assertions.decisions import assert_decision, assert_failed_decision
from parameters.auth_service import decisions as actions, wire_decisions
from src.common import fields
from src.models import decision, space
from src.storages.postgres_client import PostgresClient
from tests.fixtures import rabbitmq
from tests.fixtures.decisions import DecisionClient, new_request_header_id


def change_field(body: dict[str, Any], case: wire_decisions.InvalidField) -> None:
    """Изменяет ровно один атрибут валидного запроса."""
    parent = body
    *ancestors, field = case.path.split(".")
    for key in ancestors:
        parent = parent.setdefault(key, {})
    if case.supplied == wire_decisions.Omit.FIELD:
        parent.pop(field)
    else:
        parent[field] = case.supplied


def assert_wire_error(
    response: httpx.Response,
    correlation: str,
    delivery: rabbitmq.QueueMessage,
    *,
    body_id: bool = True,
) -> None:
    """Проверяет всё тело публичной ошибки, включая отсутствие полей решения и значений клиента."""
    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.headers["X-Request-ID"] == correlation
    error = response.json()
    message = error.pop(fields.MESSAGE_FIELD)
    assert isinstance(message, str) and message.strip()
    expected = {"error_code": "invalid_request"}
    if body_id:
        expected[fields.REQUEST_ID_FIELD] = correlation
    assert error == expected
    assert wire_decisions.PRIVATE_VALUE not in response.text
    with delivery as raw:
        assert_failed_decision(
            raw, response, correlation, code="invalid_request", stage="decode_request"
        )


@pytest.mark.parametrize(
    "case", wire_decisions.INVALID_FIELDS, ids=lambda case: case.path
)
def test_invalid_json_field(
    case: wire_decisions.InvalidField,
    actors: dict[decision.Role, decision.Actor],
    decisions: DecisionClient,
    auth_service_error_messages_from_rabbitmq: rabbitmq.QueueMessage,
) -> None:
    """Проверяет ошибки разбора запроса с пропущенным, неизвестным или некорректным полем JSON.

    Ответ 400 Bad Request описывает нарушенное ограничение без закрытого значения. Событие RabbitMQ относится
    к той же попытке. Если повреждён сам request_id, идентификатор для корреляции берётся из заголовка.
    """
    actor = actors[decision.Role.OWNER]
    body = decision.decision_request(
        actor, case.action, fields.ResourceType.SPACE, str(uuid.uuid4())
    )
    header = new_request_header_id(decisions.request_ids)
    correlation = (
        header
        if case.path == fields.REQUEST_ID_FIELD
        else body[fields.REQUEST_ID_FIELD]
    )
    decisions.request_ids.add(uuid.UUID(body[fields.REQUEST_ID_FIELD]))
    change_field(body, case)
    response = decisions.api.check_decision(
        decisions.token, actor.telegram_id, body, request_header_id=header
    )
    assert_wire_error(
        response,
        correlation,
        auth_service_error_messages_from_rabbitmq,
        body_id=case.path != fields.REQUEST_ID_FIELD,
    )
    assert response.json()[fields.MESSAGE_FIELD] == case.message


def test_invalid_authenticated_json(
    actors: dict[decision.Role, decision.Actor],
    decisions: DecisionClient,
    auth_service_error_messages_from_rabbitmq: rabbitmq.QueueMessage,
) -> None:
    """Проверяет, как сервис отвечает на незавершённый JSON после успешной аутентификации.

    Сервис возвращает 400 Bad Request с сообщением о незавершённом теле. Заголовок ответа и событие
    об ошибке разбора содержат X-Request-ID запроса, а тело ответа не содержит request_id.
    """
    actor = actors[decision.Role.OWNER]
    header = new_request_header_id(decisions.request_ids)
    response = decisions.api.check_decision(
        decisions.token, actor.telegram_id, b'{"subject":', request_header_id=header
    )
    assert_wire_error(
        response,
        header,
        auth_service_error_messages_from_rabbitmq,
        body_id=False,
    )
    assert response.json()[fields.MESSAGE_FIELD] == "body contains incomplete JSON"


@pytest.mark.parametrize(
    "case", wire_decisions.INVALID_KEYS, ids=lambda case: "+".join(case.keys)
)
def test_case_and_duplicate_keys(  # noqa: WPS211 — HTTP, очередь и БД проверяются независимо
    case: wire_decisions.InvalidKey,
    actors: dict[decision.Role, decision.Actor],
    decisions: DecisionClient,
    postgres_client: PostgresClient,
    auth_service_error_messages_from_rabbitmq: rabbitmq.QueueMessage,
) -> None:
    """Проверяет отказ при неверном регистре поля, повторе ключа или коллизии имён внутри объекта.

    Одинаковые значения повторных ключей также недопустимы. Клиент получает HTTP 400,
    а событие RabbitMQ связывает отказ с ошибкой разбора. При неоднозначном request_id
    корреляцию определяет заголовок. Ни для одного идентификатора решение не сохраняется.
    """
    actor = actors[decision.Role.VIEWER]
    body = decision.decision_request(
        actor, actions.READ, fields.ResourceType.SPACE, str(uuid.uuid4())
    )
    request_id = body[fields.REQUEST_ID_FIELD]
    decisions.request_ids.add(uuid.UUID(request_id))
    header = new_request_header_id(decisions.request_ids)
    response = decisions.api.check_decision(
        decisions.token,
        actor.telegram_id,
        case.encode(body),
        request_header_id=header,
    )
    assert_wire_error(
        response,
        request_id if case.has_body_id else header,
        auth_service_error_messages_from_rabbitmq,
        body_id=case.has_body_id,
    )
    assert case.location in response.json()[fields.MESSAGE_FIELD]
    assert not postgres_client.fetch_all(
        "SELECT 1 FROM auth.decisions WHERE request_id IN (%s, %s)",
        (request_id, header),
    )


def test_draft_route(decisions: DecisionClient) -> None:
    """Проверяет, что запрос с действующим токеном к черновому маршруту resources/decisions/check возвращает 404 Not Found."""
    response = decisions.api.client.post(
        "/api/v0/resources/decisions/check",
        json={},
        headers={"Authorization": f"Bearer {decisions.token}"},
    )
    assert response.status_code == httpx.codes.NOT_FOUND


def test_large_valid_json(
    actors: dict[decision.Role, decision.Actor],
    spaces: dict[str, str],
    decisions: DecisionClient,
) -> None:
    """Проверяет, что сервис принимает корректный запрос с дополнительным мебибайтом пробелов в конце JSON.

    Владелец получает разрешение на чтение общего пространства независимо от этого заполнения.
    """
    actor = actors[decision.Role.OWNER]
    body = decision.decision_request(
        actor, actions.READ, fields.ResourceType.SPACE, spaces[space.SpaceType.SHARED]
    )
    decisions.request_ids.add(uuid.UUID(body[fields.REQUEST_ID_FIELD]))
    raw = json.dumps(body).encode() + b" " * (1024 * 1024)
    response = decisions.api.check_decision(decisions.token, actor.telegram_id, raw)
    assert_decision(
        response, body, True, decision.DecisionReasonCode.ALLOWED_VIA_FGA_RELATION
    )
