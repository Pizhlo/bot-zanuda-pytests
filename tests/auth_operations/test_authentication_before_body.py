"""При отказе в аутентификации клиент может получить ответ до отправки тела."""

from contextlib import closing
from http.client import HTTPConnection
from uuid import uuid4

import httpx

from assertions.decisions import assert_failed_decision
from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common import fields
from tests.fixtures.rabbitmq import AuditStream

REQUEST_HEADER = "X-Request-ID"


def test_authentication_before_body(
    auth_service_v0_api_client: AuthServiceV0APIClient, audit_stream: AuditStream
) -> None:
    """Проверяет, что сервис отклоняет неаутентифицированный запрос до чтения тела.

    Клиент объявляет тело запроса и ждёт ответа, не отправляя его. Сервис возвращает 401 Unauthorized
    и использует X-Request-ID клиента в заголовке, теле ответа и событии отказа в RabbitMQ.
    """
    header = str(uuid4())
    response = post_headers_only(auth_service_v0_api_client.client.base_url, header)

    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert (
        response.headers[REQUEST_HEADER]
        == response.json()[fields.REQUEST_ID_FIELD]
        == header
    )
    with audit_stream() as raw:
        assert_failed_decision(
            raw, response, header, code="unauthorized", stage="authenticate"
        )


def post_headers_only(origin: httpx.URL, header: str) -> httpx.Response:
    """С Expect: 100-continue клиент ждёт ответ, не посылая тело. Ожидание тела обработчиком сорвёт тест по таймауту."""
    with closing(HTTPConnection(origin.host, origin.port, timeout=5)) as connection:
        connection.putrequest("POST", "/api/v0/decisions/check")
        connection.putheader(REQUEST_HEADER, header)
        connection.putheader("Content-Length", "1")
        connection.putheader("Expect", "100-continue")
        connection.endheaders()
        with connection.getresponse() as reply:
            return httpx.Response(
                reply.status, headers=reply.getheaders(), content=reply.read()
            )
