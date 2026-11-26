"""Сверяет решение для дочерней записи и перечисленные политикой поля."""

from typing import Any

import httpx

from assertions.decisions import assert_decision
from parameters.auth_service.record_decisions import RecordCase
from src.common import fields
from src.models.decision import DecisionReasonCode


def assert_record_access(
    response: httpx.Response, body: dict[str, Any], case: RecordCase
) -> None:
    """Проверяет право на существующую запись и применение маски для update."""
    granted = (
        (DecisionReasonCode.ALLOWED_VIA_FGA_RELATION, DecisionReasonCode.ALLOWED_FIELDS)
        if case.action == fields.Operation.UPDATE
        else (DecisionReasonCode.ALLOWED_VIA_FGA_RELATION,)
    )
    codes = granted if case.allowed else (DecisionReasonCode.DENIED_BY_FGA_RELATION,)
    assert_decision(response, body, case.allowed, *codes)
