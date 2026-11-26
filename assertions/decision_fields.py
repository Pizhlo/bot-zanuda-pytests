"""Маски полей и фактическое отношение для решений update."""

from typing import Any

import httpx

from assertions.decisions import assert_decision
from src.common import fields
from src.models.decision import DecisionReasonCode


def assert_mask(
    response: httpx.Response,
    body: dict[str, Any],
    mask: list[str],
    forbidden: list[str],
) -> None:
    """Проверяет решение и точный список разрешённых либо запрещённых полей."""
    allowed = not forbidden
    codes = (
        (DecisionReasonCode.ALLOWED_VIA_FGA_RELATION, DecisionReasonCode.ALLOWED_FIELDS)
        if allowed
        else (DecisionReasonCode.FORBIDDEN_FIELDS,)
    )
    decision = assert_decision(response, body, allowed, *codes)
    if allowed:
        assert_update_relation(body, decision)
    expected_fields = ", ".join(sorted(set(forbidden or mask)))
    label = "Allowed" if allowed else "Forbidden"
    assert (
        decision["reasons"][-1]["message"]
        == f"{label} fields for {body['resource']['type']}:update: {expected_fields}"
    )


def assert_update_relation(body: dict[str, Any], decision: dict[str, Any]) -> None:
    """Сверяет субъект, фактическую цель и точное право в первом объяснении update."""
    resource = "{type}:{id}".format_map(body["resource"])
    subject = "user:{id}".format_map(body["subject"])
    relation = (
        "can_manage_space"
        if body["resource"]["type"] == fields.ResourceType.SPACE
        else "can_update"
    )
    assert (
        decision["reasons"][0]["message"]
        == f'OpenFGA allowed relation "{relation}" on {resource} for {subject}'
    )
