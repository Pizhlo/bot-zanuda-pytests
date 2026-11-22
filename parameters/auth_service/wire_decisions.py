"""Невалидные поля JSON, диагностический Telegram ID и scopes сервисного клиента."""

import json
from enum import Enum
from typing import Any, NamedTuple
from uuid import UUID

from parameters.auth_service import decisions as actions
from src.common import fields


class Omit(Enum):
    FIELD = "omit"


class InvalidField(NamedTuple):
    """Путь для изменения, входное значение и безопасное ожидание HTTP-ошибки."""

    path: str
    supplied: Any
    message: str
    action: str = actions.READ


def json_member(key: str, member_value: Any) -> str:
    """Кодирует пару независимо от остальных полей, чтобы сохранить повторные ключи."""
    return f"{json.dumps(key)}: {json.dumps(member_value)}"


class InvalidKey(NamedTuple):
    """Имена, заменяющие одно поле исходного объекта, и ожидаемая диагностика."""

    field: str
    keys: tuple[str, ...]
    location: str
    parent: str | None = None
    first_value: str | None = None

    @property
    def has_body_id(self) -> bool:
        return self.field != fields.REQUEST_ID_FIELD

    def encode(self, body: dict[str, Any]) -> bytes:
        """Проверяет однозначность места подстановки и отправляет все варианты ключа в одном объекте."""
        original = (body[self.parent] if self.parent else body)[self.field]
        member = json_member(self.field, original)
        replacements = [json_member(key, original) for key in self.keys]
        if self.first_value is not None:
            replacements[0] = json_member(self.keys[0], self.first_value)
        raw = json.dumps(body)
        assert raw.count(member) == 1 and replacements != [member]
        return raw.replace(member, ", ".join(replacements), 1).encode()


INVALID_KEYS = (
    InvalidKey("subject", ("Subject",), "body"),
    InvalidKey(
        fields.NAME_FIELD,
        (fields.NAME_FIELD, fields.NAME_FIELD),
        "action.name",
        fields.ACTION_FIELD,
    ),
    InvalidKey(
        fields.NAME_FIELD, ("NAME", fields.NAME_FIELD), fields.ACTION_FIELD, fields.ACTION_FIELD, "delete"
    ),
    InvalidKey(
        fields.REQUEST_ID_FIELD,
        (fields.REQUEST_ID_FIELD, fields.REQUEST_ID_FIELD),
        fields.REQUEST_ID_FIELD,
    ),
    InvalidKey(
        fields.REQUEST_ID_FIELD,
        ("REQUEST_ID", fields.REQUEST_ID_FIELD),
        "body",
    ),
)
"""Проверяем неканонический регистр, одинаковый повтор и коллизию имён с разными действиями.
Повтор или вариант регистра идентификатора запроса делает идентификатор тела недостоверным.
"""


PRIVATE_VALUE = "test-sensitive-marker"
INVALID_FIELDS = (
    *(
        InvalidField(path, supplied, f"{path} must be a nonzero UUID")
        for path in (fields.REQUEST_ID_FIELD, "subject.id", "resource.id")
        for supplied in (Omit.FIELD, str(UUID(int=0)), PRIVATE_VALUE)
    ),
    InvalidField("resource.id", "", "resource.id must be a nonzero UUID"),
    InvalidField(
        fields.ACTION_FIELD_MASK_PATH,
        None,
        "action.attributes.field_mask must not be null",
    ),
    InvalidField(
        fields.ACTION_FIELD_MASK_PATH,
        None,
        "action.attributes.field_mask must not be null",
        action=fields.Operation.UPDATE,
    ),
    InvalidField("subject", Omit.FIELD, "subject.id must be a nonzero UUID"),
    InvalidField("subject.type", Omit.FIELD, "subject.type must be user"),
    InvalidField("subject.type", "service", "subject.type must be user"),
    InvalidField("resource", Omit.FIELD, "resource.id must be a nonzero UUID"),
    InvalidField("resource.type", Omit.FIELD, "resource.type is required"),
    InvalidField("action", Omit.FIELD, "action.name is required"),
    InvalidField("action.name", Omit.FIELD, "action.name is required"),
    InvalidField(
        "subject.relation", PRIVATE_VALUE, "subject contains an unknown field"
    ),
    InvalidField(
        "subject.attributes.is_admin",
        True,
        "subject.attributes contains an unknown field",
    ),
    InvalidField("user_id", PRIVATE_VALUE, "body contains an unknown field"),
    InvalidField("resource.id", None, "resource.id must not be null"),
    InvalidField("subject", None, "subject must not be null"),
    InvalidField(
        fields.ACTION_FIELD_MASK_PATH,
        PRIVATE_VALUE,
        "action.attributes.field_mask must be an array",
    ),
    InvalidField(
        fields.ACTION_FIELD_MASK_PATH,
        ["title", 42],
        "action.attributes.field_mask[1] must be a string",
    ),
    InvalidField(
        "options.consistency",
        PRIVATE_VALUE,
        "options.consistency must be higher_consistency or minimize_latency",
    ),
    InvalidField(
        "options.include_reasons",
        PRIVATE_VALUE,
        "options.include_reasons must be a boolean",
    ),
    InvalidField("options", None, "options must not be null"),
    InvalidField(
        "subject.attributes.telegram_user_id",
        "0123",
        "subject.attributes.telegram_user_id must be a positive decimal int64 without spaces, signs or leading zeros",
    ),
)
"""Ошибки после успешной аутентификации, до вычисления решения.

- Обязательные идентификаторы отсутствуют, равны нулю или имеют неверный формат: 400 Bad Request с путём поля.
- Неполные subject/action/resource, удалённое поле и null: 400 Bad Request с нарушенным ограничением.
- При обновлении пространства field_mask=null: 400 Bad Request с точной причиной и аудитом decode_request.
- Тип маски, её элемента, options или диагностического Telegram ID некорректен: 400 Bad Request.
"""
