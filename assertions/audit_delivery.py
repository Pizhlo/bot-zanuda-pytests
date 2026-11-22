"""Контракт итогового аудита при доступном брокере и после разрыва соединения."""

from typing import Any

from src.common import fields
from src.storages.postgres_client import PostgresClient


DECISION_RESULT_FIELD = "result"


def assert_completed(event: dict[str, Any], decision: dict[str, Any]) -> None:
    """Сверяет опубликованные ID и исход с данными конкретного HTTP-ответа."""
    expected = {
        "status": "completed",
        "level": "info",
        "kind": "domain",
        "operation": "check_decision",
        fields.REQUEST_ID_FIELD: decision[fields.REQUEST_ID_FIELD],
    }
    assert {key: event[key] for key in expected} == expected
    assert (
        event["context"][fields.DECISION_ID_FIELD] == decision[fields.DECISION_ID_FIELD]
    )
    assert event["context"]["decision"] == decision[DECISION_RESULT_FIELD]


def assert_saved_delivery(
    postgres_client: PostgresClient, decision: dict[str, Any]
) -> None:
    """Подтверждает сохранённый результат, даже если брокер не принял аудит."""
    saved = postgres_client.fetch_one(
        "SELECT result FROM auth.decisions WHERE decision_id = %s AND request_id = %s",
        (decision["decision_id"], decision[fields.REQUEST_ID_FIELD]),
    )
    assert saved == {DECISION_RESULT_FIELD: decision[DECISION_RESULT_FIELD]}


def assert_delivery_log(logs: str, decision: dict[str, Any]) -> None:
    """Проверяет локальное completed-событие и сообщение об отказе отправки для одного request_id."""
    lines = [
        line for line in logs.splitlines() if decision[fields.REQUEST_ID_FIELD] in line
    ]
    assert any(
        "audit event" in line
        and decision["decision_id"] in line
        and f"decision:{decision['result']}" in line
        and "completed" in line
        for line in lines
    )
    assert any("decision audit delivery failed" in line for line in lines)
