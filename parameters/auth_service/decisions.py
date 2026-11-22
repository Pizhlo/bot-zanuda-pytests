"""Типы ресурсов и действия для сценариев decisions/check."""

import pytest

from src.models.decision import DecisionReasonCode, Role

READ = "read"


REPEATED_READ_CASES = (
    pytest.param(
        Role.OWNER,
        True,
        {
            "result": "allow",
            "reason_codes": [DecisionReasonCode.ALLOWED_VIA_FGA_RELATION],
            "checked_relation": "can_view",
        },
        id="owner-read-twice",
    ),
    pytest.param(
        Role.OUTSIDER,
        False,
        {
            "result": "deny",
            "reason_codes": [DecisionReasonCode.DENIED_BY_FGA_RELATION],
            "checked_relation": "can_view",
        },
        id="outsider-read-twice",
    ),
)
"""Повторное чтение общего пространства с тем же request_id без запроса объяснений.

- Владелец запрашивает чтение дважды: 200 OK, allow в обоих ответах.
- Посторонний запрашивает чтение дважды: 200 OK, deny в обоих ответах.

Каждая попытка получает свой decision_id и строку в PostgreSQL с причиной и версиями политик.
"""
