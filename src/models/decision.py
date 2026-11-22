"""Запросы к публичному контракту decisions/check."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import uuid4

from src.common import fields

type DecisionAttributes = Mapping[str, str | list[str]]


class Consistency(StrEnum):
    """Режим согласованности, передаваемый в options.consistency запроса decisions/check."""

    HIGHER_CONSISTENCY = "higher_consistency"
    MINIMIZE_LATENCY = "minimize_latency"


class DecisionReasonCode(StrEnum):
    """Код причины решения, возвращаемый API и сохраняемый в PostgreSQL."""

    ALLOWED_VIA_FGA_RELATION = "allowed_via_fga_relation"
    DENIED_BY_FGA_RELATION = "denied_by_fga_relation"
    ALLOWED_FIELDS = "allowed_fields"
    FORBIDDEN_FIELDS = "forbidden_fields"
    ALLOWED_FOR_REGISTERED_USER = "allowed_for_registered_user"
    FIRST_PERSONAL_SPACE = "first_personal_space"
    PERSONAL_SPACE_ALREADY_EXISTS = "personal_space_already_exists"
    PROTECTED_SPACE_OWNER = "protected_space_owner"


class Role(StrEnum):
    """Обозначает роль в тестовом пространстве. OUTSIDER зарегистрирован в БД и не имеет членства."""

    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"
    OUTSIDER = "outsider"


@dataclass(frozen=True)
class Actor:
    """Связывает внутренний UUID пользователя с Telegram ID из доверенного HTTP-заголовка."""

    user_id: str
    telegram_id: str


def decision_request(  # noqa: WPS211 — две независимые группы атрибутов API
    actor: Actor,
    action: str,
    kind: str,
    object_id: str,
    *,
    action_attributes: DecisionAttributes | None = None,
    resource_attributes: DecisionAttributes | None = None,
) -> dict[str, Any]:
    """Собирает запрос проверки от имени зарегистрированного пользователя.
    Каждый вызов получает новый request_id. Для проверки повтора сценарий отправляет
    готовое тело дважды. По умолчанию API запрашивается с объяснениями и повышенной согласованностью.
    """
    return {
        fields.REQUEST_ID_FIELD: str(uuid4()),
        fields.SUBJECT_FIELD: {
            fields.TYPE_FIELD: fields.ResourceType.USER,
            fields.ID_FIELD: actor.user_id,
        },
        fields.ACTION_FIELD: {
            fields.NAME_FIELD: action,
            fields.ATTRIBUTES_FIELD: action_attributes or {},
        },
        fields.RESOURCE_FIELD: {
            fields.TYPE_FIELD: kind,
            fields.ID_FIELD: object_id,
            fields.ATTRIBUTES_FIELD: resource_attributes or {},
        },
        fields.OPTIONS_FIELD: {
            fields.INCLUDE_REASONS_FIELD: True,
            fields.CONSISTENCY_FIELD: Consistency.HIGHER_CONSISTENCY,
        },
    }
