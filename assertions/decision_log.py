"""Сопоставление локальных структурированных событий процесса auth-service с HTTP и историей решений."""

import re
import shlex
import socket
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import pytest

from parameters.auth_service.decision_history import Operation
from parameters.auth_service.wire_decisions import PRIVATE_VALUE
from src.common import fields
from tests.fixtures.service_log import ServiceLog

type Payload = dict[str, Any]
MODEL_ID = "authorization_model_id"


def log_fields(tokens: Iterable[str], separator: str) -> dict[str, str]:
    """Разделяет имя и значение по первому разделителю, сохраняя двоеточия в именах объектов OpenFGA и серверном времени."""
    attributes = {}
    for token in tokens:
        key, found, field_text = token.partition(separator)
        if found:
            attributes[key] = field_text
    return attributes


def completed_contexts(
    log: ServiceLog, request_id: str, token: str, count: int = 1
) -> list[dict[str, str]]:
    """Читает все события запроса в порядке записи. Проверяет отсутствие секретов и в остальных строках процесса."""
    output = log.wait(request_id, 'msg="audit event"', count)
    if (
        (token and token in output)
        or PRIVATE_VALUE in output
        or re.search(r"\bauthorization\s*[:=]", output, re.IGNORECASE)
    ):
        pytest.fail(
            "В логе тестового процесса обнаружены данные авторизации или недоверенного контекста"
        )

    contexts = []
    for line in output.splitlines():
        if 'msg="audit event"' in line and request_id in line:
            event = log_fields(shlex.split(line), "=")
            if event.get(fields.REQUEST_ID_FIELD) == request_id:
                contexts.append(completed_context(event))
    return contexts


def completed_context(event: dict[str, str]) -> dict[str, str]:
    """Разбирает поле context в формате map[...] текстового обработчика Go slog для тестовых операций."""
    assert (event["service_name"], event["operation"], event["status"]) == (
        "auth-service",
        "check_decision",
        "completed",
    )
    assert (event["kind"], event["level"]) == ("domain", "info")
    raw = event["context"]
    assert raw.startswith("map[") and raw.endswith("]")
    # Текстовый map Go не экранирует значения. Для сравниваемых скалярных полей
    # пробел разделяет пары. Свободный текст требует структурированного формата.
    tokens = raw[4:-1].split()
    if any(":" not in token for token in tokens):
        pytest.fail("Неоднозначное значение с пробелом в текстовом контексте аудита")
    context = log_fields(tokens, ":")
    assert context["stage"] == "completed"
    return context


def assert_operation_context(
    ctx: dict[str, str], decision: Payload, body: Payload, case: Operation
) -> None:
    """Сверяет данные события с запросом, ожидаемой операцией и фактическим HTTP-ответом."""
    meta = decision["meta"]
    resource = body["resource"]
    attrs = resource["attributes"]
    target = attrs.get("space_id") or resource["id"]
    expected = {
        "caller": "bot",
        "subject": meta["subject"],
        "action": case.action,
        "resource": meta["resource"],
        "checked_object": f"space:{target}" if case.relation else "<nil>",
        "checked_relation": case.relation or "<nil>",
        "decision": decision["result"],
        fields.DECISION_ID_FIELD: decision[fields.DECISION_ID_FIELD],
        "policy_version": meta["policy_version"],
        MODEL_ID: meta[MODEL_ID],
    }
    if case.action == "create" and case.kind == "space":
        expected["space_type"] = attrs["space_type"]
    if case.kind == "member":
        expected.update(
            target_user_id=resource["id"],
            role=body["action"]["attributes"]["role"],
            target_is_owner="false",
        )
    assert {key: ctx[key] for key in expected} == expected


def assert_server_origin(ctx: dict[str, str], begin: datetime, end: datetime) -> None:
    """Проверяет время обработки и адрес реального клиента, отправившего запрос по сети стенда."""
    assert begin <= datetime.fromisoformat(ctx["timestamp"]) <= end
    client_addresses = socket.gethostbyname_ex(socket.gethostname())[2]
    assert ctx["ip_address"].rsplit(":", 1)[0] in client_addresses


def completed_for_decision(
    log: ServiceLog, decision: Payload, token: str
) -> dict[str, str]:
    """Читает единственное событие конкретного HTTP-запроса и сверяет UUID принятого решения."""
    contexts = completed_contexts(log, decision[fields.REQUEST_ID_FIELD], token)
    assert len(contexts) == 1
    assert contexts[0][fields.DECISION_ID_FIELD] == decision[fields.DECISION_ID_FIELD]
    return contexts[0]


def assert_logged_replay(
    log: ServiceLog, responses: tuple[Payload, Payload], token: str
) -> None:
    """Требует ровно два события с общим request_id и разными decision_id, по одному для каждого HTTP-ответа."""
    first, second = responses
    assert first[fields.DECISION_ID_FIELD] != second[fields.DECISION_ID_FIELD]
    contexts = completed_contexts(log, first[fields.REQUEST_ID_FIELD], token, count=2)
    actual = [(ctx[fields.DECISION_ID_FIELD], ctx["decision"]) for ctx in contexts]
    assert actual == [
        (resp[fields.DECISION_ID_FIELD], resp["result"]) for resp in responses
    ]
