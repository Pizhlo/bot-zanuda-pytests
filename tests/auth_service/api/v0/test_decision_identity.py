"""Идентификация на decisions/check через Telegram и реально выданные scopes."""

from collections.abc import Callable

import httpx
import pytest

from assertions.decisions import (
    assert_decision,
    assert_failed_decision,
    assert_invalid_response,
)
from parameters.auth_service import decision_identity as cases
from src.common import fields
from src.models import decision as model
from src.storages.postgres_client import PostgresClient
from tests.fixtures import decisions as clients
from tests.fixtures import owner_request as owners
from tests.fixtures import rabbitmq


@pytest.mark.parametrize("case", cases.TOKEN_CASES)
def test_decision_service_token(
    case: cases.TokenCase,
    scoped_token: Callable[[cases.TokenCase], str],
    owner_request: owners.OwnerRequest,
    decisions: clients.DecisionClient,
    auth_service_error_messages_from_rabbitmq: rabbitmq.QueueMessage,
) -> None:
    """Проверяет, какой токен сервисного клиента даёт право запрашивать решения.

    Некорректный или просроченный токен даёт 401 Unauthorized. Для действующего токена необходима выданная
    привилегия bot. Похожее имя привилегии и наличие невыданной привилегии приводят к 403 Forbidden.
    Каждый отказ попадает в аудит.
    """
    actor, body = owner_request
    header = clients.new_request_header_id(decisions.request_ids)
    response = decisions.api.check_decision(
        scoped_token(case), actor.telegram_id, body, request_header_id=header
    )
    assert response.status_code == case.status
    if case.code is None:
        assert_decision(
            response, body, True, model.DecisionReasonCode.ALLOWED_VIA_FGA_RELATION
        )
    else:
        assert (
            response.json()[fields.REQUEST_ID_FIELD]
            == response.headers["X-Request-ID"]
            == header
        )
        with auth_service_error_messages_from_rabbitmq as raw:
            assert_failed_decision(
                raw, response, header, code=case.code, stage="authenticate"
            )


def test_unregistered_telegram(
    unregistered_telegram: str,
    owner_request: owners.OwnerRequest,
    decisions: clients.DecisionClient,
    postgres_client: PostgresClient,
    auth_service_error_messages_from_rabbitmq: rabbitmq.QueueMessage,
) -> None:
    """Проверяет, что запрос решения для неизвестного пользователя Telegram не регистрирует его в сервисе.

    Сервис возвращает 404 Not Found, а в RabbitMQ появляется событие user_not_found для этого запроса.
    """
    _, body = owner_request
    query = "SELECT user_id FROM users.telegram WHERE tg_id = %s"
    response = decisions.api.check_decision(
        decisions.token, unregistered_telegram, body
    )
    assert response.status_code == httpx.codes.NOT_FOUND
    assert not postgres_client.fetch_all(query, (int(unregistered_telegram),))
    with auth_service_error_messages_from_rabbitmq as raw:
        assert_failed_decision(
            raw,
            response,
            body[fields.REQUEST_ID_FIELD],
            code="user_not_found",
            stage="verify_subject",
        )


@pytest.mark.parametrize("telegram", (None, "", "01"))
def test_invalid_telegram(
    telegram: str | None,
    owner_request: owners.OwnerRequest,
    decisions: clients.DecisionClient,
    auth_service_error_messages_from_rabbitmq: rabbitmq.QueueMessage,
) -> None:
    """Проверяет отклонение запроса без корректного заголовка X-Telegram-User-Id.

    Если заголовок отсутствует, пуст или содержит число с ведущим нулём, сервис возвращает 400 Bad Request,
    указывает неверный заголовок и публикует событие отказа на этапе проверки личности.
    """
    _, body = owner_request
    response = decisions.api.check_decision(decisions.token, telegram, body)
    expected = "X-Telegram-User-Id header is required"
    if telegram:
        expected = "X-Telegram-User-Id header must be a positive decimal int64 without spaces, signs or leading zeros"
    assert_invalid_response(response, body[fields.REQUEST_ID_FIELD], expected)
    with auth_service_error_messages_from_rabbitmq as raw:
        assert_failed_decision(
            raw,
            response,
            body[fields.REQUEST_ID_FIELD],
            code="invalid_request",
            stage="verify_subject",
        )


def test_matching_telegram(
    owner_request: owners.OwnerRequest, decisions: clients.DecisionClient
) -> None:
    """Проверяет, что совпадение Telegram ID владельца в теле и заголовке позволяет ему получить разрешение на чтение.

    Для принятого запроса решение содержит request_id из тела, даже если в заголовке передан другой UUID.
    """
    actor, body = owner_request
    body[fields.SUBJECT_FIELD][fields.ATTRIBUTES_FIELD] = {
        fields.TELEGRAM_USER_ID_FIELD: actor.telegram_id
    }
    response = decisions.api.check_decision(
        decisions.token,
        actor.telegram_id,
        body,
        request_header_id=clients.new_request_header_id(decisions.request_ids),
    )
    assert_decision(
        response, body, True, model.DecisionReasonCode.ALLOWED_VIA_FGA_RELATION
    )


def test_login_without_grants(
    empty_scope_credentials: dict[str, str],
    owner_request: owners.OwnerRequest,
    decisions: clients.DecisionClient,
    auth_service_error_messages_from_rabbitmq: rabbitmq.QueueMessage,
) -> None:
    """Проверяет доступ активного сервисного клиента без предоставленных привилегий.

    Клиент может получить токен при входе. Попытка запросить решение с этим токеном даёт 403 Forbidden
    и событие отказа в RabbitMQ.
    """
    login = decisions.api.login(empty_scope_credentials)
    assert login.status_code == httpx.codes.OK
    header = clients.new_request_header_id(decisions.request_ids)
    response = decisions.api.check_decision(
        login.json()["access_token"],
        owner_request[0].telegram_id,
        owner_request[1],
        request_header_id=header,
    )
    assert response.status_code == httpx.codes.FORBIDDEN
    with auth_service_error_messages_from_rabbitmq as raw:
        assert_failed_decision(
            raw, response, header, code="forbidden", stage="authenticate"
        )
