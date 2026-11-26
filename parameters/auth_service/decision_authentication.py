"""Заголовок корреляции и тело запроса без токена."""

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest


@dataclass(frozen=True)
class Rejection:
    """Задаёт входной заголовок и вид тела запроса для проверки корреляции отказа."""

    header: str | None
    valid_header: bool = False
    malformed_json: bool = False


UNAUTHORIZED_CASES = (
    pytest.param(Rejection(str(uuid4()), valid_header=True), id="provided"),
    pytest.param(Rejection(None), id="missing"),
    pytest.param(Rejection("not-a-uuid"), id="malformed-header"),
    pytest.param(Rejection(str(UUID(int=0))), id="zero"),
    pytest.param(Rejection(None, malformed_json=True), id="malformed-json"),
    pytest.param(
        Rejection(str(uuid4()), valid_header=True, malformed_json=True),
        id="malformed-json-valid-header",
    ),
)
"""Запрос без токена. Идентификатор из тела запроса не используется для корреляции раннего отказа.

- Заголовок X-Request-ID содержит ненулевой UUID: 401 Unauthorized, этот UUID в заголовке, теле ответа и аудите.
- Повреждённый JSON и корректный X-Request-ID: 401 Unauthorized, UUID заголовка совпадает в HTTP-ответе и событии аудита.
- Заголовок отсутствует: 401 Unauthorized, новый UUID в заголовке ответа и аудите, в теле ответа request_id
  отсутствует.
- Заголовок содержит строку вместо UUID: 401 Unauthorized, новый UUID только в заголовке ответа и аудите.
- Заголовок содержит нулевой UUID: 401 Unauthorized, новый UUID только в заголовке ответа и аудите.
- Заголовка нет и JSON повреждён: 401 Unauthorized, новый UUID. В аудите указан этап authenticate.
"""
