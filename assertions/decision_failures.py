"""Содержимое обязательного аудита при отказах зависимостей decisions/check."""

from typing import Any
from uuid import UUID

from parameters.auth_service.decision_faults import Fault
from src.common import audit
from tests.fixtures.rabbitmq import QueueMessage


def assert_failure_audit(
    delivery: QueueMessage, fault: Fault, request_id: str, model_id: str
) -> None:
    """Сверяет отказ с конкретным запросом и проверяет границу, на которой уже вычислено решение."""
    with delivery as raw:
        assert raw is not None
        event = audit.AuditMessage.model_validate_json(raw)
        assert (
            event.request_id,
            event.operation,
            event.status,
            event.error_code,
            event.message,
        ) == (
            request_id,
            "check_decision",
            audit.Status.FAILED,
            fault.code,
            fault.message,
        )
        context = event.context or {}
        assert context["stage"] == fault.stage
        check_failure_stage(context, fault, model_id)


def check_failure_stage(context: dict[str, Any], fault: Fault, model_id: str) -> None:
    """Только сбой сохранения следует после вычисления decision_id и обеих версий."""
    if fault.dependency == "storage":
        expected = "deny" if fault.scenario == "deny" else "allow"
        assert UUID(context["decision_id"]).int and context["decision"] == expected
        assert context["authorization_model_id"] == model_id and context[
            "policy_version"
        ].startswith("casbin:sha256:")
    else:
        assert "decision_id" not in context and "decision" not in context
