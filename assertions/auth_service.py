"""Проверки сообщений аудита auth-service."""

from uuid import UUID

import pytest

from src.common import audit


def assert_audit_payload(
    message: bytes | None,
    expected: audit.AuditMessage | None,
    missing_message: str = "Нет сообщений в очереди",
) -> None:
    """Сверяет событие отказа. Успешный запрос оставляет очередь ошибок пустой."""
    if expected is None:
        assert message is None, "Успешный запрос опубликовал событие в очереди ошибок"
        return
    if not message:
        pytest.fail(missing_message)
    actual = audit.AuditMessage.model_validate_json(message)
    assert actual.request_id and UUID(actual.request_id).int, "Нет идентификатора запроса в событии аудита"
    audit.assert_audit_message(expected, actual)
    audit.assert_audit_message_context(expected, actual)
