"""Прямая синхронизация пространства без предварительной проверки decisions/check."""

from typing import NamedTuple

from src.common.fields import ChangeType
from src.models.space import SpaceType


class PrivacyCase(NamedTuple):
    """Исходный тип, присланный тип, операция и подмена владельца для прямой записи."""

    stored: SpaceType | None
    requested: str | list[str] | None
    change: ChangeType
    foreign_owner: bool = False


PRIVACY_CASES = (
    PrivacyCase(SpaceType.SHARED, SpaceType.PERSONAL, ChangeType.MEMBERSHIP_CHANGED),
    PrivacyCase(None, None, ChangeType.RESOURCE_ADDED),
    PrivacyCase(None, "private", ChangeType.RESOURCE_ADDED),
    PrivacyCase(None, ["personal", "shared"], ChangeType.RESOURCE_ADDED),
    PrivacyCase(None, SpaceType.PERSONAL, ChangeType.RESOURCE_ADDED, True),
    PrivacyCase(SpaceType.PERSONAL, None, ChangeType.RESOURCE_REMOVED),
    PrivacyCase(SpaceType.PERSONAL, SpaceType.SHARED, ChangeType.RESOURCE_REMOVED),
    PrivacyCase(SpaceType.SHARED, SpaceType.PERSONAL, ChangeType.RESOURCE_REMOVED),
    *(
        PrivacyCase(kind, None, change)
        for kind in SpaceType
        for change in (
            ChangeType.MEMBERSHIP_ADDED,
            ChangeType.MEMBERSHIP_CHANGED,
            ChangeType.MEMBERSHIP_REMOVED,
        )
    ),
)
"""Для каждого запроса используется произвольный decision_id и два независимых ключа идемпотентности.

- Создание без типа, с неизвестным типом, двумя типами или чужим владельцем: 400 Bad Request.
- Изменение роли обычного участника shared с подменой типа на personal: 400 Bad Request.
- Удаление личного пространства или подмена сохранённого типа: 400 Bad Request.
- Добавление, смена или удаление участника personal и изменение членства владельца shared: 400 Bad Request.
После каждого отказа проверяются прежние связи пространства и личные отметки обоих пользователей.
"""
