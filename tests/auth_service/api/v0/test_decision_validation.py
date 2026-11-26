"""Контракт допустимых действий и атрибутов для решения."""

from typing import Any
from uuid import uuid4

import httpx
import pytest

from assertions.decisions import (
    assert_decision,
    assert_failed_decision,
    assert_invalid_response,
)
from parameters.auth_service import decision_validation as cases
from parameters.auth_service import decisions as decision_params
from src.common import fields
from src.models.decision import (
    Actor,
    DecisionAttributes,
    DecisionReasonCode,
    Role,
    decision_request,
)
from src.models.space import SpaceType
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.rabbitmq import QueueMessage


def assert_invalid(
    response: httpx.Response,
    request_id: str,
    expected_message: str,
    delivery: QueueMessage,
    *,
    stage: str = "validate_request",
) -> None:
    """Проверяет путь ошибочного поля и корреляцию HTTP 400 с исходным запросом."""
    assert_invalid_response(response, request_id, expected_message)

    with delivery as message:
        assert_failed_decision(
            message, response, request_id, code="invalid_request", stage=stage
        )


@pytest.mark.parametrize(("kind", "action"), cases.UNSUPPORTED_ACTION_CASES)
def test_unsupported_action(
    kind: str,
    action: str,
    actors: dict[Role, Actor],
    decisions: DecisionClient,
    auth_service_error_messages_from_rabbitmq: QueueMessage,
) -> None:
    """Проверяет отказ при действии, которое не поддерживается для выбранного типа ресурса.

    Сервис возвращает 400 Bad Request, указывает несовместимость действия с типом ресурса и публикует
    событие об ошибке валидации с идентификатором этой попытки.
    """
    actor = actors[Role.OWNER]
    attrs = (
        {fields.FIELD_MASK_FIELD: [fields.TITLE_FIELD]}
        if action == fields.Operation.UPDATE
        else {}
    )
    parent = (
        {fields.SPACE_ID_FIELD: str(uuid4())} if kind == decision_params.MEMBER else {}
    )
    body = decision_request(
        actor,
        action,
        kind,
        str(uuid4()),
        action_attributes=attrs,
        resource_attributes=parent,
    )
    assert_invalid(
        decisions.check_single_action(actor, body),
        body[fields.REQUEST_ID_FIELD],
        "action.name is not supported for resource.type",
        auth_service_error_messages_from_rabbitmq,
    )


@pytest.mark.parametrize(
    ("kind", "action", "action_attrs", "resource_attrs", "expected_message", "stage"),
    cases.INVALID_ATTRIBUTE_CASES,
)
def test_attributes_belong_to_operation(  # noqa: WPS211 — запрос, ожидаемое поле и фикстуры
    kind: str,
    action: str,
    action_attrs: DecisionAttributes,
    resource_attrs: DecisionAttributes,
    expected_message: str,
    actors: dict[Role, Actor],
    decisions: DecisionClient,
    stage: str,
    auth_service_error_messages_from_rabbitmq: QueueMessage,
) -> None:
    """Проверяет обязательные и недопустимые атрибуты при запросе решения для разных операций.

    Если атрибут пропущен, имеет неверное значение или относится к другой операции, сервис возвращает
    400 Bad Request с указанием ограничения. В аудите отражается этап, на котором обнаружена ошибка.
    """
    actor = actors[Role.OWNER]
    body = decision_request(
        actor,
        action,
        kind,
        str(uuid4()),
        action_attributes=action_attrs,
        resource_attributes=resource_attrs,
    )
    assert_invalid(
        decisions.check_single_action(actor, body),
        body[fields.REQUEST_ID_FIELD],
        expected_message,
        auth_service_error_messages_from_rabbitmq,
        stage=stage,
    )


def test_relation_denial_precedes_field_policy(
    actors: dict[Role, Actor],
    spaces: dict[str, str],
    decisions: DecisionClient,
) -> None:
    """Проверяет, какая причина отказа возвращается зрителю при попытке изменить владельца общего пространства.

    Зритель не имеет права обновлять пространство. Сервис возвращает deny по отношению OpenFGA,
    даже если запрошенная маска сама содержит запрещённое поле owner_id.
    """
    viewer = actors[Role.VIEWER]
    body = decision_request(
        viewer,
        fields.Operation.UPDATE,
        fields.ResourceType.SPACE,
        spaces[SpaceType.SHARED],
        action_attributes={fields.FIELD_MASK_FIELD: ["owner_id"]},
    )
    assert_decision(
        decisions.check_single_action(viewer, body),
        body,
        False,
        DecisionReasonCode.DENIED_BY_FGA_RELATION,
    )


@pytest.mark.parametrize(("options", "codes"), cases.DECISION_OPTION_CASES)
def test_decision_options(
    options: dict[str, Any],
    codes: tuple[DecisionReasonCode, ...],
    actors: dict[Role, Actor],
    decisions: DecisionClient,
) -> None:
    """Проверяет, как параметры ответа влияют на объяснение разрешённого создания общего пространства.

    При higher_consistency с отключённым include_reasons объяснения нет. При minimize_latency с включённым
    include_reasons решение указывает, что создание разрешено зарегистрированному пользователю.
    """
    actor = actors[Role.EDITOR]
    body = decision_request(
        actor,
        fields.Operation.CREATE,
        fields.ResourceType.SPACE,
        str(uuid4()),
        resource_attributes={fields.SPACE_TYPE_FIELD: SpaceType.SHARED},
    )
    body[fields.OPTIONS_FIELD] = options
    assert_decision(decisions.check_single_action(actor, body), body, True, *codes)
