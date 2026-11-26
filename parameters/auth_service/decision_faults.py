"""Внешний отказ, публичная ошибка и этап аудита проверки решения."""

from typing import NamedTuple


class Fault(NamedTuple):
    dependency: str
    code: str
    stage: str
    message: str
    scenario: str = "update"


DEPENDENCY_FAILURES = (
    Fault(
        "identity",
        "identity_store_unavailable",
        "verify_subject",
        "Identity store is unavailable",
    ),
    Fault(
        "openfga",
        "openfga_unavailable",
        "check_relation",
        "Relationship check is unavailable",
    ),
    Fault(
        "openfga",
        "openfga_unavailable",
        "check_relation",
        "Relationship check is unavailable",
        "shared",
    ),
    Fault(
        "openfga",
        "openfga_unavailable",
        "check_relation",
        "Relationship check is unavailable",
        "personal",
    ),
    Fault(
        "storage",
        "decision_store_unavailable",
        "save_decision",
        "Decision store is unavailable",
        "deny",
    ),
    Fault(
        "storage",
        "decision_store_unavailable",
        "save_decision",
        "Decision store is unavailable",
    ),
)
"""Отказ отдельной зависимости для корректного запроса: 503 Service Unavailable.

- Поиск личности блокируется только на чтении пользователей: нет завершённого решения.
- OpenFGA недоступен после готовности сервиса: нет результата проверки отношения.
- Запись решения заблокирована: в событии есть вычисленное решение и его версии, в БД строки нет.
"""
