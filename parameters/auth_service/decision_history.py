"""Операции с различными запрошенными ресурсами и объектами проверки OpenFGA."""

from typing import NamedTuple

from parameters.auth_service import decisions as actions
from src.common import fields
from src.models.decision import DecisionReasonCode, Role


class Operation(NamedTuple):
    """Задаёт запрос и независимое ожидание объяснения и связи."""

    kind: str
    action: str
    relation: str | None
    reason: DecisionReasonCode


OPERATIONS = (
    Operation(
        fields.ResourceType.SPACE,
        fields.Operation.UPDATE,
        "can_manage_space",
        DecisionReasonCode.ALLOWED_VIA_FGA_RELATION,
    ),
    Operation(
        fields.ResourceType.NOTE,
        fields.Operation.CREATE,
        "can_create_note",
        DecisionReasonCode.ALLOWED_VIA_FGA_RELATION,
    ),
    Operation(
        actions.MEMBER,
        actions.EDIT,
        "can_manage_members",
        DecisionReasonCode.ALLOWED_VIA_FGA_RELATION,
    ),
    Operation(
        fields.ResourceType.SPACE,
        fields.Operation.CREATE,
        None,
        DecisionReasonCode.ALLOWED_FOR_REGISTERED_USER,
    ),
)
"""Каждый запрос владельца возвращает 200 OK и записывается в историю.
- Для space:update сохраняются UUID пространства и запрошенная маска name.
- Создание заметки проверяет can_create_note на родительском пространстве.
- Изменение роли другого пользователя проверяет can_manage_members, сохраняет цель и новую роль.
- Создание shared разрешено зарегистрированному пользователю без checked_object и checked_relation.
"""


class CompletedRead(NamedTuple):
    """Роль инициатора и ожидаемый исход чтения, доставляемый через RabbitMQ."""

    role: Role
    allowed: bool
    reason: DecisionReasonCode


BROKER_READS = (
    CompletedRead(Role.OWNER, True, DecisionReasonCode.ALLOWED_VIA_FGA_RELATION),
    CompletedRead(Role.OUTSIDER, False, DecisionReasonCode.DENIED_BY_FGA_RELATION),
)
"""Чтение общего пространства: 200 OK. Владелец получает allow, посторонний deny.
В обоих случаях в очереди появляется completed с исходом и идентификаторами HTTP-ответа.
"""


class DeniedMember(NamedTuple):
    """Причина отказа и ожидаемое представление дополнительной проверки в текстовом журнале."""

    role: Role
    reason: DecisionReasonCode
    owner_result: str | None


DENIED_MEMBERS = (
    DeniedMember(Role.OWNER, DecisionReasonCode.PROTECTED_SPACE_OWNER, "true"),
    DeniedMember(Role.OUTSIDER, DecisionReasonCode.DENIED_BY_FGA_RELATION, None),
)
"""Попытка удалить владельца общего пространства.
- Владелец: 200 OK, deny. В событии записан успешный результат проверки owner для цели.
- Посторонний: 200 OK, deny по can_manage_members. Поле дополнительной проверки отсутствует.
"""
