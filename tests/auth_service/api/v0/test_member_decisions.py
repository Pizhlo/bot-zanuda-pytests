"""Изменение состава и ролей участников через decisions/check."""

from uuid import uuid4

import pytest

from assertions.decisions import (
    assert_decision,
    assert_failed_decision,
    assert_invalid_response,
)
from parameters.auth_service import decisions as decision_params
from parameters.auth_service import member_decisions as cases
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

ACTION_AND_ROLE = ("action", "assigned")


@pytest.mark.parametrize("case", cases.membership_cases(), ids=str)
def test_manage_membership(
    case: cases.Membership,
    actors: dict[Role, Actor],
    spaces: dict[str, str],
    decisions: DecisionClient,
) -> None:
    """Проверяет, кто может добавить участника, сменить его роль или удалить его из пространства.

    В общем пространстве владелец и администратор могут управлять составом, в том числе администратор
    может изменить собственную роль или удалить себя. Редактор, зритель и посторонний получают отказ.
    В личном пространстве изменение состава запрещено всем, включая владельца.
    """
    actor = actors[case.caller]
    body = decision_request(
        actor,
        case.action,
        decision_params.MEMBER,
        actors[case.target].user_id,
        action_attributes={fields.ROLE_FIELD: case.assigned} if case.assigned else {},
        resource_attributes={fields.SPACE_ID_FIELD: spaces[case.kind]},
    )
    code = (
        DecisionReasonCode.ALLOWED_VIA_FGA_RELATION
        if case.allowed
        else DecisionReasonCode.DENIED_BY_FGA_RELATION
    )
    assert_decision(
        decisions.check_single_action(actor, body), body, case.allowed, code
    )


@pytest.mark.parametrize("role", cases.MANAGERS)
@pytest.mark.parametrize("change", cases.MEMBERSHIP_ACTIONS, ids=str)
def test_protected_space_owner(
    role: Role,
    change: cases.RoleChange,
    actors: dict[Role, Actor],
    spaces: dict[str, str],
    decisions: DecisionClient,
) -> None:
    """Проверяет, что владельцу и администратору запрещено менять членство владельца общего пространства.

    При добавлении, смене роли и удалении сервис возвращает deny с причиной protected_space_owner
    и UUID защищённого владельца. При добавлении и смене роли запрет действует для любой назначаемой роли.
    """
    actor = actors[role]
    owner = actors[Role.OWNER]
    body = decision_request(
        actor,
        change.action,
        decision_params.MEMBER,
        owner.user_id,
        action_attributes={fields.ROLE_FIELD: change.assigned}
        if change.assigned
        else {},
        resource_attributes={fields.SPACE_ID_FIELD: spaces[SpaceType.SHARED]},
    )
    response = assert_decision(
        decisions.check_single_action(actor, body),
        body,
        False,
        DecisionReasonCode.PROTECTED_SPACE_OWNER,
    )
    space_id = spaces[SpaceType.SHARED]
    assert response["reasons"][0]["message"] == (
        f"Membership of user:{owner.user_id} cannot be changed because they own space:{space_id}"
    )


@pytest.mark.parametrize(ACTION_AND_ROLE, cases.MEMBERSHIP_ACTIONS)
@pytest.mark.parametrize(
    "kind", ["untyped", "conflicting", "unknown", SpaceType.SHARED]
)
def test_membership_unknown_target(  # noqa: WPS211 — сценарий и фикстуры стенда
    kind: str,
    action: str,
    assigned: Role | None,
    actors: dict[Role, Actor],
    spaces: dict[str, str],
    decisions: DecisionClient,
) -> None:
    """Проверяет решение администратора об изменении членства пользователя с неизвестным UUID.

    В общем пространстве добавление, смена роли и удаление разрешены. Существование цели проверяет бизнес-сервис.
    Если неизвестно само пространство, его тип отсутствует или указан противоречиво, сервис отказывает.
    """
    actor = actors[Role.ADMIN]
    body = decision_request(
        actor,
        action,
        decision_params.MEMBER,
        str(uuid4()),
        action_attributes={fields.ROLE_FIELD: assigned} if assigned else {},
        resource_attributes={fields.SPACE_ID_FIELD: spaces.get(kind) or str(uuid4())},
    )
    # Проверка полномочия администратора отделена от проверки существования пользователя бизнес-сервисом.
    allowed = kind == SpaceType.SHARED
    code = (
        DecisionReasonCode.ALLOWED_VIA_FGA_RELATION
        if allowed
        else DecisionReasonCode.DENIED_BY_FGA_RELATION
    )
    assert_decision(decisions.check_single_action(actor, body), body, allowed, code)


@pytest.mark.parametrize(
    ("action", "attrs", "expected_message"), cases.INVALID_MEMBERSHIP_CASES
)
def test_invalid_membership_attributes(  # noqa: WPS211 — входные данные и фикстуры HTTP и RabbitMQ
    action: str,
    attrs: DecisionAttributes,
    expected_message: str,
    actors: dict[Role, Actor],
    spaces: dict[str, str],
    decisions: DecisionClient,
    auth_service_error_messages_from_rabbitmq: QueueMessage,
) -> None:
    """Проверяет, какие атрибуты допустимы при добавлении участника, смене роли и удалении.

    Сервис отклоняет пропущенную или недопустимую роль при добавлении и смене роли, роль при удалении
    и лишнюю маску полей. Ответ 400 Bad Request указывает нарушенное ограничение, а аудит фиксирует отказ.
    """
    actor = actors[Role.OWNER]
    body = decision_request(
        actor,
        action,
        decision_params.MEMBER,
        actors[Role.VIEWER].user_id,
        action_attributes=attrs,
        resource_attributes={fields.SPACE_ID_FIELD: spaces[SpaceType.SHARED]},
    )
    response = decisions.check_single_action(actor, body)
    assert_invalid_response(response, body[fields.REQUEST_ID_FIELD], expected_message)

    with auth_service_error_messages_from_rabbitmq as message:
        assert_failed_decision(
            message,
            response,
            body[fields.REQUEST_ID_FIELD],
            code="invalid_request",
            stage="validate_request",
        )


@pytest.mark.parametrize(ACTION_AND_ROLE, cases.MEMBERSHIP_ACTIONS)
def test_admin_manages_another_admin(
    action: str,
    assigned: Role | None,
    actors: dict[Role, Actor],
    peer_admin_space: str,
    decisions: DecisionClient,
) -> None:
    """Проверяет, что администратор общего пространства может управлять членством другого администратора.

    Добавление и смена роли разрешены для каждой назначаемой роли. Удаление разрешено без указания роли.
    """
    actor = actors[Role.ADMIN]
    body = decision_request(
        actor,
        action,
        decision_params.MEMBER,
        actors[Role.EDITOR].user_id,
        action_attributes={fields.ROLE_FIELD: assigned} if assigned else {},
        resource_attributes={fields.SPACE_ID_FIELD: peer_admin_space},
    )
    assert_decision(
        decisions.check_single_action(actor, body),
        body,
        True,
        DecisionReasonCode.ALLOWED_VIA_FGA_RELATION,
    )
