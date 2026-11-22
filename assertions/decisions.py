"""Проверки публичного результата и объяснения решения."""

import re
from operator import itemgetter
from typing import Any
from uuid import UUID

import httpx

from src.common import audit, fields
from src.models.decision import DecisionReasonCode
from src.storages.postgres_client import PostgresClient


def assert_decision(
    response: httpx.Response,
    body: dict[str, Any],
    allowed: bool,
    *codes: DecisionReasonCode,
) -> dict[str, Any]:
    """Проверяет HTTP-ответ, исход решения и ресурс, к которому применены политики."""
    assert response.status_code == httpx.codes.OK, response.text
    decision: dict[str, Any] = response.json()

    assert decision[fields.REQUEST_ID_FIELD] == body[fields.REQUEST_ID_FIELD]
    assert UUID(decision[fields.DECISION_ID_FIELD]).int > 0

    assert_decision_result(decision, allowed, codes)
    assert_decision_meta(decision["meta"], body)
    return decision


def assert_decision_result(
    decision: dict[str, Any], allowed: bool, codes: tuple[DecisionReasonCode, ...]
) -> None:
    """Сверяет оба представления исхода и упорядоченные причины с ожиданиями кейса."""
    assert decision["allow"] is allowed
    expected_result = "allow" if allowed else "deny"
    assert decision["result"] == expected_result

    reasons = decision["reasons"]
    assert [reason["code"] for reason in reasons] == list(codes)
    assert all(reason["message"].strip() for reason in reasons)


def assert_decision_meta(meta: dict[str, Any], body: dict[str, Any]) -> None:
    """Сверяет участника, действие и объект запроса, затем версии политик и время проверки."""
    expected = {
        fields.SUBJECT_FIELD: "user:{id}".format_map(body[fields.SUBJECT_FIELD]),
        fields.ACTION_FIELD: body[fields.ACTION_FIELD][fields.NAME_FIELD],
        fields.RESOURCE_FIELD: "{type}:{id}".format_map(body[fields.RESOURCE_FIELD]),
    }
    assert {key: meta[key] for key in expected} == expected

    assert re.fullmatch(r"casbin:sha256:[0-9a-f]{64}", meta["policy_version"])
    assert meta["authorization_model_id"]
    assert meta["latency_ms"] >= 0


def assert_failed_decision(
    message: bytes | None,
    response: httpx.Response,
    request_id: str,
    *,
    code: str,
    stage: str,
) -> None:
    """Связывает отказ HTTP с единственным событием ошибки RabbitMQ по UUID, причине и этапу."""
    assert response.json()["error_code"] == code
    assert message is not None
    event = audit.AuditMessage.model_validate_json(message)

    expected = {
        "service_name": audit.AUTH_SERVICE_NAME,
        "operation": "check_decision",
        "status": audit.Status.FAILED,
        "kind": audit.Kind.DOMAIN,
        "level": audit.Level.ERROR,
        fields.REQUEST_ID_FIELD: request_id,
        "error_code": code,
        "message": response.json()["message"],
        "user_id": None,
    }
    assert event.model_dump(include=set(expected)) == expected
    assert event.context and event.context[audit.STAGE_FIELD] == stage
    assert fields.DECISION_ID_FIELD not in event.context


def assert_saved_reads(
    postgres: PostgresClient,
    body: dict[str, Any],
    expected: dict[str, object],
    responses: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Сравнивает строки обеих попыток с ожиданиями кейса по их отдельным decision_id."""
    expected_rows = [
        {
            **expected,
            "subject_id": UUID(body[fields.SUBJECT_FIELD][fields.ID_FIELD]),
            "checked_object": "space:{id}".format_map(body[fields.RESOURCE_FIELD]),
            fields.DECISION_ID_FIELD: UUID(response[fields.DECISION_ID_FIELD]),
            "policy_version": response["meta"]["policy_version"],
            "authorization_model_id": response["meta"]["authorization_model_id"],
        }
        for response in responses
    ]
    rows = postgres.fetch_all(
        "SELECT decision_id, subject_id, result, ARRAY(SELECT reason->>'code' FROM json_array_elements(reasons) AS reason) AS reason_codes, "
        "checked_object, checked_relation, policy_version, authorization_model_id "
        "FROM auth.decisions WHERE request_id = %s ORDER BY decision_id",
        (body[fields.REQUEST_ID_FIELD],),
    )
    assert rows == sorted(expected_rows, key=itemgetter(fields.DECISION_ID_FIELD))
