"""Токены активного временного сервисного клиента с выданными scopes bot и admin."""

from typing import NamedTuple

import httpx
import pytest

VALID = "valid"


class TokenCase(NamedTuple):
    """Ожидаемый HTTP-результат для предъявленного набора scopes."""

    scope: str
    mode: str
    status: int
    code: str | None


TOKEN_CASES = (
    pytest.param(
        TokenCase("bot", "invalid", httpx.codes.UNAUTHORIZED, "unauthorized"),
        id="malformed",
    ),
    pytest.param(
        TokenCase("bot", "expired", httpx.codes.UNAUTHORIZED, "unauthorized"),
        id="expired",
    ),
    pytest.param(
        TokenCase("admin bot", VALID, httpx.codes.OK, None), id="issued-bot-and-admin"
    ),
    pytest.param(
        TokenCase("admin", VALID, httpx.codes.FORBIDDEN, "forbidden"), id="no-bot"
    ),
    pytest.param(
        TokenCase("not-bot", VALID, httpx.codes.FORBIDDEN, "forbidden"), id="substring"
    ),
    pytest.param(
        TokenCase("bot unissued", VALID, httpx.codes.FORBIDDEN, "forbidden"),
        id="unissued",
    ),
)
"""Проверка scope на самом decisions/check до декодирования тела.

- Некорректный или просроченный JWT: 401 Unauthorized.
- Обе выданные роли, среди которых есть точный bot: 200 OK, allow.
- Только admin, not-bot или bot вместе с невыданным scope: 403 Forbidden.
"""
