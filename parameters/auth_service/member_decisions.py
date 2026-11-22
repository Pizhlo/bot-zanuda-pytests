"""Ожидаемые полномочия для изменения ролей в пространствах."""

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import product
from typing import NamedTuple

import pytest

from parameters.auth_service import decisions as decision_params
from src.common import fields
from src.models.decision import Role
from src.models.space import SpaceType

MANAGERS = (Role.OWNER, Role.ADMIN)


class RoleChange(NamedTuple):
    """Описывает изменение состава. Удаление участника передаётся без назначаемой роли."""

    action: str
    assigned: Role | None

    def __str__(self) -> str:
        return f"{self.action}-{self.assigned or 'no-role'}"


MEMBERSHIP_ACTIONS = (
    *(
        RoleChange(action, role)
        for action in (decision_params.ADD, decision_params.EDIT)
        for role in (Role.ADMIN, Role.EDITOR, Role.VIEWER)
    ),
    RoleChange(decision_params.REMOVE, None),
)
"""Действия над участником общего пространства с проверкой каждой допустимой роли.

- Владелец или администратор добавляет участника с ролью admin, editor или viewer: 200 OK, allow.
- Владелец или администратор назначает участнику одну из этих ролей через edit: 200 OK, allow.
- Владелец или администратор удаляет участника без указания роли: 200 OK, allow.
- Целевой участник сам является владельцем: 200 OK, deny (protected_space_owner) для всех трёх действий.

Те же варианты используются для проверки личных пространств, других ролей и неизвестного UUID.
"""


@dataclass(frozen=True)
class Membership:
    """Связывает роль инициатора и цели с типом пространства, действием и ожидаемым правом."""

    kind: SpaceType
    caller: Role
    target: Role
    action: str
    assigned: Role | None
    allowed: bool

    def __str__(self) -> str:
        change = RoleChange(self.action, self.assigned)
        parts = (self.kind, self.caller, str(change), self.target)
        return "-".join(parts)


def membership_cases() -> Iterator[Membership]:
    """Строит сочетания инициатора, цели и назначаемой роли для обоих типов пространства.
    Попытки менеджера изменить владельца проверяются отдельно со специальной причиной отказа.
    """
    for kind, caller, target in product(
        (SpaceType.SHARED, SpaceType.PERSONAL), Role, Role
    ):
        can_manage = kind == SpaceType.SHARED and caller in MANAGERS
        if target == Role.OWNER and can_manage:
            continue
        for change in MEMBERSHIP_ACTIONS:
            yield Membership(kind, caller, target, *change, can_manage)


ROLE_REQUIRED = (
    "action.attributes.role must be viewer, editor or admin for member add/edit"
)
ROLE_UNEXPECTED = "action.attributes.role is only supported for member add/edit"
MASK_UNEXPECTED = "action.attributes.field_mask is only supported for update"

INVALID_MEMBERSHIP_CASES = (
    pytest.param(decision_params.ADD, {}, ROLE_REQUIRED, id="add-missing"),
    pytest.param(decision_params.EDIT, {}, ROLE_REQUIRED, id="edit-missing"),
    pytest.param(
        decision_params.ADD,
        {fields.ROLE_FIELD: "owner"},
        ROLE_REQUIRED,
        id="assign-owner",
    ),
    pytest.param(
        decision_params.EDIT,
        {fields.ROLE_FIELD: "unknown"},
        ROLE_REQUIRED,
        id="unknown-role",
    ),
    pytest.param(
        decision_params.REMOVE,
        {fields.ROLE_FIELD: "viewer"},
        ROLE_UNEXPECTED,
        id="remove-with-role",
    ),
    pytest.param(
        decision_params.ADD,
        {fields.ROLE_FIELD: "admin", fields.FIELD_MASK_FIELD: [fields.NAME_FIELD]},
        MASK_UNEXPECTED,
        id="add-with-mask",
    ),
)
"""Проверка атрибутов действия при управлении составом от имени владельца.

- Добавление участника без role: 400 Bad Request.
- Смена роли без role: 400 Bad Request.
- Попытка назначить owner при добавлении: 400 Bad Request.
- Попытка назначить неизвестную роль при редактировании: 400 Bad Request.
- При удалении передан role=viewer: 400 Bad Request.
- При добавлении с role=admin также передан field_mask: 400 Bad Request.

Ответ содержит только invalid_request, точное описание нарушенного ограничения и request_id попытки.
"""
