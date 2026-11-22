"""Корреляция раннего отказа и сверка заявленной личности."""

from contextlib import AbstractContextManager
from uuid import UUID, uuid4

import httpx
import pytest

from assertions.decisions import assert_failed_decision, assert_invalid_response
from parameters.auth_service import decision_authentication as cases
from parameters.auth_service import decisions as decision_params
from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common import fields
from src.models.decision import Actor, Role, decision_request
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.rabbitmq import QueueMessage

HEADER = "X-Request-ID"


def assert_rejection_id(
    response: httpx.Response, body_id: str, header: str | None, valid: bool
) -> str:
    """Сверяет корреляцию раннего 401 в заголовке и теле ответа.
    UUID из отклонённого тела запроса не должен становиться идентификатором аудита.
    """
    assert response.status_code == httpx.codes.UNAUTHORIZED
    correlation = response.headers[HEADER]
    assert UUID(correlation).int and correlation != body_id
    error = response.json()
    assert error["error_code"] == "unauthorized"
    if valid:
        assert correlation == header == error[fields.REQUEST_ID_FIELD]
    else:
        assert fields.REQUEST_ID_FIELD not in error
    return correlation


@pytest.mark.parametrize("case", cases.UNAUTHORIZED_CASES)
def test_unauthorized_correlation(
    case: cases.Rejection,
    actors: dict[Role, Actor],
    auth_service_v0_api_client: AuthServiceV0APIClient,
    decision_request_ids: set[UUID],
    auth_service_error_messages_from_rabbitmq: AbstractContextManager[bytes | None],
) -> None:
    """Проверяет, как сервис связывает ранний отказ в аутентификации с событием RabbitMQ.

    Без JWT сервис возвращает 401 Unauthorized даже для повреждённого JSON. Корректный X-Request-ID
    попадает в ответ и аудит. При отсутствующем, нулевом или некорректном заголовке сервис выдаёт новый UUID
    в заголовке ответа и аудите, а идентификатор из тела запроса не использует.
    """
    actor = actors[Role.OWNER]
    body = decision_request(
        actor, decision_params.READ, fields.ResourceType.SPACE, str(uuid4())
    )
    decision_request_ids.add(UUID(body[fields.REQUEST_ID_FIELD]))
    if case.valid_header and case.header is not None:
        decision_request_ids.add(UUID(case.header))

    response = auth_service_v0_api_client.check_decision(
        None,
        actor.telegram_id,
        b"{" if case.malformed_json else body,
        request_header_id=case.header,
    )
    correlation = assert_rejection_id(
        response, body[fields.REQUEST_ID_FIELD], case.header, case.valid_header
    )
    with auth_service_error_messages_from_rabbitmq as message:
        assert_failed_decision(
            message, response, correlation, code="unauthorized", stage="authenticate"
        )


def test_telegram_attribute_must_match_header(
    actors: dict[Role, Actor],
    decisions: DecisionClient,
    auth_service_error_messages_from_rabbitmq: QueueMessage,
) -> None:
    """Проверяет, что зритель не может приписать себе Telegram ID владельца в атрибутах запроса.

    При расхождении с X-Telegram-User-Id сервис возвращает 400 Bad Request, указывает ошибочное поле
    и публикует событие об отказе на этапе проверки личности.
    """
    viewer = actors[Role.VIEWER]
    body = decision_request(
        viewer, decision_params.READ, fields.ResourceType.SPACE, str(uuid4())
    )
    body[fields.SUBJECT_FIELD][fields.ATTRIBUTES_FIELD] = {
        fields.TELEGRAM_USER_ID_FIELD: actors[Role.OWNER].telegram_id
    }
    response = decisions.check_single_action(viewer, body)
    assert_invalid_response(
        response,
        body[fields.REQUEST_ID_FIELD],
        "subject.attributes.telegram_user_id must match the X-Telegram-User-Id header",
    )

    with auth_service_error_messages_from_rabbitmq as message:
        assert_failed_decision(
            message,
            response,
            body[fields.REQUEST_ID_FIELD],
            code="invalid_request",
            stage="verify_subject",
        )
