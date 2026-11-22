"""Права на существующее пространство, создание и изменение полей."""

from dataclasses import dataclass

import pytest

from parameters.auth_service import decisions as decision_params
from src.common import fields
from src.models.decision import DecisionReasonCode, Role
from src.models.space import SpaceType

SHARED_READERS = (Role.OWNER, Role.ADMIN, Role.EDITOR, Role.VIEWER)
OWNER_ONLY = (Role.OWNER,)
SPACE_ACCESS_CASES = (
    (SpaceType.SHARED, decision_params.READ, SHARED_READERS),
    (SpaceType.SHARED, fields.Operation.UPDATE, OWNER_ONLY),
    (SpaceType.SHARED, fields.Operation.DELETE, OWNER_ONLY),
    (SpaceType.PERSONAL, decision_params.READ, OWNER_ONLY),
    (SpaceType.PERSONAL, fields.Operation.UPDATE, OWNER_ONLY),
    (SpaceType.PERSONAL, fields.Operation.DELETE, ()),
    *(
        (kind, action, ())
        for kind in ("untyped", "conflicting", "unknown")
        for action in (
            decision_params.READ,
            fields.Operation.UPDATE,
            fields.Operation.DELETE,
        )
    ),
)
"""Чтение, переименование и удаление существующего пространства.

- Чтение общего пространства владельцем, администратором, редактором или зрителем: 200 OK, allow.
- Чтение общего пространства посторонним пользователем: 200 OK, deny.
- Переименование или удаление общего пространства владельцем: 200 OK, allow.
- Те же действия администратора, редактора, зрителя или постороннего: 200 OK, deny.
- Чтение или переименование личного пространства владельцем: 200 OK, allow.
- Чтение или переименование чужого личного пространства при любой роли: 200 OK, deny.
- Удаление личного пространства при любой роли, включая владельца: 200 OK, deny.
- UUID неизвестен, у пространства нет типа или отмечены оба типа: 200 OK, deny при каждом действии и роли.
"""


@dataclass(frozen=True)
class SpaceCreation:
    """Задаёт ожидаемый исход создания пространства и код причины для роли инициатора."""

    kind: SpaceType
    role: Role
    allowed: bool
    reason: DecisionReasonCode

    def __str__(self) -> str:
        return f"{self.kind}-{self.role}-{self.reason}"


SPACE_CREATION_CASES = (
    *(
        SpaceCreation(
            SpaceType.SHARED,
            role,
            True,
            DecisionReasonCode.ALLOWED_FOR_REGISTERED_USER,
        )
        for role in Role
    ),
    SpaceCreation(
        SpaceType.PERSONAL,
        Role.OWNER,
        False,
        DecisionReasonCode.PERSONAL_SPACE_ALREADY_EXISTS,
    ),
    *(
        SpaceCreation(
            SpaceType.PERSONAL, role, True, DecisionReasonCode.FIRST_PERSONAL_SPACE
        )
        for role in Role
        if role != Role.OWNER
    ),
)
"""Проверка права зарегистрированного пользователя создать пространство.

- Создание общего пространства с любой ролью, включая постороннего: 200 OK, allow (allowed_for_registered_user).
- Создание первого личного пространства без отметки has_personal_space: 200 OK, allow (first_personal_space).
- У владельца уже есть отметка has_personal_space: 200 OK, deny (personal_space_already_exists).
"""


SPACE_FIELD_CASES = (
    pytest.param([fields.NAME_FIELD, fields.NAME_FIELD], True, id="repeated-name"),
    pytest.param([fields.TITLE_FIELD], False, id="title"),
    pytest.param(["participants"], False, id="participants"),
    pytest.param(["members"], False, id="members"),
    pytest.param(["owner_id"], False, id="owner-id"),
    pytest.param([fields.SPACE_TYPE_FIELD], False, id="space-type"),
    pytest.param([fields.NAME_FIELD, "unknown"], False, id="mixed-fields"),
)
"""Владелец обновляет общее или личное пространство с указанной маской полей.

- Поле name указано дважды: 200 OK, allow (allowed_fields).
- Владелец передаёт title для общего или личного пространства: 200 OK, deny (forbidden_fields).
- Изменение participants или members через space:update: 200 OK, deny.
- В маске только owner_id: 200 OK, deny (forbidden_fields).
- В маске только space_type: 200 OK, deny (forbidden_fields).
- Вместе с name запрошено неизвестное поле: 200 OK, deny для всей маски (forbidden_fields).
"""
