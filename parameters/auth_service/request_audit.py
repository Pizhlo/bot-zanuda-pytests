"""Ожидания для ранних отказов HTTP-маршрутов с единым событием аудита."""

from src.common import audit


def validation_failure(
    operation: audit.Operation,
    code: str,
    detail: str,
    *,
    level: audit.Level = audit.Level.WARN,
    stage: str = audit.AUTHENTICATE,
) -> audit.AuditMessage:
    """Описывает первое нарушение входного запроса, которое должно попасть в очередь ошибок.
    Текст причины сверяется отдельно от уровня, операции и этапа обработки.
    """
    return audit.AuditMessage(
        service_name=audit.AUTH_SERVICE_NAME,
        operation=operation,
        status=audit.Status.FAILED,
        level=level,
        kind=audit.Kind.VALIDATION,
        error_code=code,
        message=detail,
        cause=detail,
        context={"stage": stage, "user_agent": audit.TEST_USER_AGENT},
    )


def rejected_client(operation: audit.Operation) -> audit.AuditMessage:
    """Формирует ожидание отказа, когда проверка сервисного клиента завершилась ошибкой."""
    return validation_failure(
        operation, "SERVICE_INVALID", "Service client verification failed"
    )


def missing_telegram_header(operation: audit.Operation) -> audit.AuditMessage:
    """Описывает отказ защищённого маршрута до сверки личности при отсутствии Telegram-заголовка."""
    return validation_failure(
        operation, "VALIDATION_FAILED", "Telegram user header is missing"
    )


def malformed_telegram_header(operation: audit.Operation) -> audit.AuditMessage:
    """Ожидает warning этапа authenticate до поиска пользователя в PostgreSQL."""
    return validation_failure(operation, "VALIDATION_FAILED", "Telegram user ID must be a positive decimal int64")
