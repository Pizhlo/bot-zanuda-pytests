"""Неоднозначный X-Request-ID на входе в штатный сервис."""

from uuid import UUID, uuid4

import httpx

from assertions.decisions import assert_failed_decision
from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common import fields
from tests.fixtures.rabbitmq import AuditStream
from tests.fixtures.service_log import ServiceLog


def test_duplicated_header_warning(
    auth_service_v0_api_client: AuthServiceV0APIClient,
    main_log: ServiceLog,
    audit_stream: AuditStream,
) -> None:
    """Проверяет корреляцию раннего отказа, если запрос без JWT дважды передал одинаковый X-Request-ID.

    Сервис возвращает 401 Unauthorized и новый UUID в заголовке ответа. Этот UUID связывает предупреждение
    в журнале с событием RabbitMQ. В теле ответа идентификатора запроса нет.
    """
    header = str(uuid4())
    response = auth_service_v0_api_client.client.post(
        "/api/v0/decisions/check",
        headers=[("X-Request-ID", header), ("X-Request-ID", header)],
        content=b"{",
    )
    correlation = response.headers["X-Request-ID"]
    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert UUID(correlation).int and correlation != header
    assert fields.REQUEST_ID_FIELD not in response.json()
    main_log.assert_warning(correlation)
    with audit_stream() as raw:
        assert_failed_decision(
            raw, response, correlation, code="unauthorized", stage="authenticate"
        )
