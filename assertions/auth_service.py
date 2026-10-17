"""Проверки сообщений аудита auth-service."""

import pytest

from src.common import audit


def assert_audit_payload(
    message: bytes | None,
    expected: audit.AuditMessage | None,
    missing_message: str = "Нет сообщений в очереди",
) -> None:
    """Проверяет ожидаемый аудит; без ожидания не проверяет содержимое очереди."""
    if expected is None:
        return
    if not message:
        pytest.fail(missing_message)
    actual = audit.AuditMessage.model_validate_json(message)
    audit.assert_audit_message(expected, actual)
    audit.assert_audit_message_context(expected, actual)
