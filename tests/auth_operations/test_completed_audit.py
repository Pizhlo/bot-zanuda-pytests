"""Аудит решений в stdout тестового процесса при штатном фильтре уровней RabbitMQ."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from assertions import decision_log
from assertions.decisions import assert_decision
from parameters.auth_service import decision_history as cases
from parameters.auth_service import decisions as actions
from src.common import fields
from src.models import decision as model
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.operation_requests import operation_request, send_operation
from tests.fixtures.service_log import ServiceLog


@pytest.mark.parametrize(
    "case", cases.OPERATIONS, ids=lambda case: f"{case.kind}-{case.action}"
)
def test_completed_operation(  # noqa: WPS211 — HTTP, модель и журнал проверяются независимо
    case: cases.Operation,
    decisions: DecisionClient,
    main_log: ServiceLog,
    actors: dict[model.Role, model.Actor],
    spaces: dict[str, str],
    model_id: str,
) -> None:
    """Проверяет, какие сведения о завершённой проверке прав попадают в локальный аудит.

    Сценарии охватывают изменение пространства, создание заметки, смену роли участника и создание общего
    пространства. Для каждой операции ожидается одно событие с контекстом соответствующего решения
    и временем сервера. В журнале не должно быть токена клиента.
    """
    begin = datetime.now(UTC)
    body = operation_request(case, actors, spaces["shared"])
    decision = send_operation(decisions, actors[model.Role.OWNER], body, case)
    assert decision["meta"][decision_log.MODEL_ID] == model_id
    event = decision_log.completed_for_decision(main_log, decision, decisions.token)
    decision_log.assert_operation_context(event, decision, body, case)
    decision_log.assert_server_origin(event, begin, datetime.now(UTC))


def test_first_personal_audit(
    decisions: DecisionClient,
    main_log: ServiceLog,
    actors: dict[model.Role, model.Actor],
) -> None:
    """Проверяет аудит разрешения на создание первого личного пространства пользователя.

    Итоговое событие указывает тип personal и проверку отметки has_personal_space у этого пользователя.
    """
    actor = actors[model.Role.OUTSIDER]
    body = model.decision_request(
        actor,
        fields.Operation.CREATE,
        fields.ResourceType.SPACE,
        str(uuid4()),
        resource_attributes={fields.SPACE_TYPE_FIELD: "personal"},
    )
    decision = assert_decision(
        decisions.check_single_action(actor, body),
        body,
        True,
        model.DecisionReasonCode.FIRST_PERSONAL_SPACE,
    )
    event = decision_log.completed_for_decision(main_log, decision, decisions.token)
    assert (
        event["space_type"],
        event["checked_object"],
        event["checked_relation"],
    ) == ("personal", f"user:{actor.user_id}", "has_personal_space")


@pytest.mark.parametrize("case", cases.DENIED_MEMBERS, ids=lambda case: case.role)
def test_denied_member_audit(
    case: cases.DeniedMember,
    decisions: DecisionClient,
    main_log: ServiceLog,
    actors: dict[model.Role, model.Actor],
    spaces: dict[str, str],
) -> None:
    """Проверяет, как аудит объясняет отказ удалить владельца общего пространства.

    Для самого владельца событие фиксирует успешную проверку роли цели. Постороннему пользователю
    отказывают уже при проверке права управлять участниками, поэтому результат проверки роли цели отсутствует.
    """
    actor = actors[case.role]
    body = model.decision_request(
        actor,
        actions.REMOVE,
        actions.MEMBER,
        actors[model.Role.OWNER].user_id,
        resource_attributes={fields.SPACE_ID_FIELD: spaces["shared"]},
    )
    decision = assert_decision(
        decisions.check_single_action(actor, body), body, False, case.reason
    )
    event = decision_log.completed_for_decision(main_log, decision, decisions.token)
    assert event["target_user_id"] == actors[model.Role.OWNER].user_id
    assert event.get("target_is_owner") == case.owner_result
