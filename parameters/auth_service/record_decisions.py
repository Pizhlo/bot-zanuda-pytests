"""Ожидаемые права на собственную и чужую запись, независимо от хранилища."""

from collections.abc import Iterator
from dataclasses import dataclass
from types import MappingProxyType

from parameters.auth_service import decisions as decision_params
from src.common import fields
from src.models.decision import Role
from src.models.space import SpaceType

UNKNOWN_PARENT = "unknown"

# Действия над чужой записью в общем пространстве по роли инициатора.
SHARED_RIGHTS = MappingProxyType(
    {
        Role.OWNER: (
            decision_params.READ,
            fields.Operation.UPDATE,
            fields.Operation.DELETE,
        ),
        Role.ADMIN: (decision_params.READ, fields.Operation.UPDATE),
        Role.EDITOR: (decision_params.READ, fields.Operation.UPDATE),
        Role.VIEWER: (decision_params.READ,),
        Role.OUTSIDER: (),
    }
)


@dataclass(frozen=True)
class RecordCase:
    """Связывает роль инициатора и автора с ожидаемым правом в заданном пространстве."""

    space: str
    actor: Role
    author: Role
    action: str
    allowed: bool

    def __str__(self) -> str:
        return f"{self.space}-{self.actor}-{self.action}-by-{self.author}"


def record_cases(actions: tuple[str, ...]) -> Iterator[RecordCase]:
    """Перебирает роли инициатора и автора для каждого действия в shared и personal.
    Ожидаемый доступ берётся из матрицы ролей, отдельно учитываются авторство и владелец пространства.
    """
    for actor in Role:
        for author in Role:
            for action in actions:
                has_shared_access = actor == author or action in SHARED_RIGHTS[actor]
                yield from (
                    RecordCase(
                        SpaceType.SHARED, actor, author, action, has_shared_access
                    ),
                    RecordCase(
                        SpaceType.PERSONAL,
                        actor,
                        author,
                        action,
                        actor == Role.OWNER,
                    ),
                )


def damaged_parent_cases(actions: tuple[str, ...]) -> Iterator[RecordCase]:
    """Формирует ожидания для отсутствующего объекта и повреждённых связей с пространством.
    В случае двух родителей оба пространства принадлежат одному владельцу.
    """
    for space in ("untyped", "conflicting", "orphan", UNKNOWN_PARENT, "two_parents"):
        for actor in Role:
            for action in actions:
                # Участник shared не может получить доступ к чужой personal-записи
                # через вторую связь. Здесь оба пространства принадлежат одному владельцу.
                allowed = space == "two_parents" and actor == Role.OWNER
                yield RecordCase(space, actor, Role.VIEWER, action, allowed)


CREATORS: MappingProxyType[str, tuple[Role, ...]] = MappingProxyType(
    {
        SpaceType.SHARED: (Role.OWNER, Role.ADMIN, Role.EDITOR),
        SpaceType.PERSONAL: (Role.OWNER,),
    }
)
ACTIONS = (decision_params.READ, fields.Operation.UPDATE, fields.Operation.DELETE)


RECORD_ACCESS_CASES = (*record_cases(ACTIONS), *damaged_parent_cases(ACTIONS))
"""Чтение, обновление и удаление заметки. В запросе передан другой space_id, права определяет сохранённый родитель.

- Автор работает со своей записью в общем пространстве, даже без членства: 200 OK, allow для всех трёх действий.
- Владелец общего пространства работает с чужой записью: 200 OK, allow для всех трёх действий.
- Администратор или редактор читает либо обновляет чужую запись: 200 OK, allow. При удалении: 200 OK, deny.
- Зритель читает чужую запись: 200 OK, allow. При обновлении или удалении: 200 OK, deny.
- Посторонний обращается к чужой записи общего пространства: 200 OK, deny для всех трёх действий.
- Владелец личного пространства обращается к записи любого автора: 200 OK, allow для всех трёх действий.
- Другой пользователь обращается к записи личного пространства, даже собственной: 200 OK, deny.
- Запись неизвестна, лишена родителя, у родителя нет типа или указаны оба типа: 200 OK, deny при любой роли.
- У записи два родителя (shared и personal) с одним владельцем: 200 OK, allow у этого владельца.
- Та же запись с двумя родителями, запрос от любого другого пользователя: 200 OK, deny.
"""


RECORD_CREATION_CASES = tuple(
    (parent, role, role in CREATORS.get(parent, ()))
    for parent in (
        SpaceType.SHARED,
        SpaceType.PERSONAL,
        "untyped",
        "conflicting",
        UNKNOWN_PARENT,
    )
    for role in Role
)
"""Проверка права создать заметку. В объяснении решения сверяем UUID родительского пространства.

- Общее пространство, инициатор owner, admin или editor: 200 OK, allow.
- Общее пространство, инициатор viewer или посторонний: 200 OK, deny.
- Личное пространство, инициатор владелец: 200 OK, allow.
- Личное пространство, любой другой инициатор: 200 OK, deny.
- Пространство неизвестно, у него нет типа или одновременно отмечены shared и personal: 200 OK, deny при любой
  роли.
"""


type FieldCase = tuple[list[str], list[str]]

RECORD_FIELD_CASES: tuple[FieldCase, ...] = (
    (["text"], []),
    ([fields.TITLE_FIELD], []),
    ([fields.TITLE_FIELD, "text", fields.TITLE_FIELD], []),
    (["remind_at"], ["remind_at"]),
    (["created"], ["created"]),
    (
        [
            "last_edit",
            fields.TITLE_FIELD,
            "unknown",
            "last_edit",
        ],
        ["last_edit", "unknown"],
    ),
)
"""Владелец обновляет собственную заметку в общем пространстве.

- В маске только text или только title: 200 OK, allow.
- В маске title, text и повтор title: 200 OK, allow, каждое поле перечислено один раз.
- Запрошено поле напоминания remind_at: 200 OK, deny, указано remind_at.
- Запрошено техническое поле created: 200 OK, deny, указано created.
- Вместе с title запрошены last_edit дважды и unknown: 200 OK, deny для всей маски, указаны last_edit и unknown.
"""
