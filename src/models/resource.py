import re

from dataclasses import dataclass, fields as dataclass_fields, is_dataclass
from enum import Enum
from typing import Any


REF_SEPARATOR = ":"
META_KEY = "meta"


def format_ref(resource_type: str, resource_id: str) -> str:
    """Форматирует ссылку на ресурс в формате type:id."""
    return REF_SEPARATOR.join((resource_type, resource_id))


@dataclass(frozen=True)
class ResourceRef:
    """Ссылка на ресурс или связанную сущность."""

    type: str
    id: str


@dataclass(frozen=True)
class ResourceWithAttributes(ResourceRef):
    """Ресурс для создания пространства и успешного ответа синхронизации."""

    attributes: dict[str, str] | None = None


@dataclass(frozen=True)
class ResourceRelations:
    """Связи ресурса с другими сущностями."""

    owner: ResourceRef | None = None
    parent: ResourceRef | None = None


@dataclass(frozen=True)
class ResourceEventContext:
    """Контекст события изменения ресурса."""

    source_service: str
    event_type: str


@dataclass(frozen=True)
class ResourceChangeMessage:
    """Сообщение об изменении ресурса (создание, обновление, удаление)."""

    request_id: str
    resource: ResourceRef
    operation: str
    change_type: str
    relations: ResourceRelations | None
    context: ResourceEventContext


@dataclass(frozen=True)
class AuthTuple:
    """Запись в модели авторизации (subject, relation, resource)."""

    subject: str
    relation: str
    resource: str


@dataclass(frozen=True)
class ResourceChangeMeta:
    """Метаданные ответа на изменение ресурса."""

    auth_model_id: str | None = None


@dataclass(frozen=True)
class ResourceChangeResponse:
    """Ответ на изменение ресурса."""

    request_id: str
    idempotency_key: str
    status: str
    operation_result: str
    resource: ResourceRef
    written_tuples: tuple[AuthTuple, ...]
    deleted_tuples: tuple[AuthTuple, ...]
    meta: ResourceChangeMeta


@dataclass(frozen=True)
class DetailedError:
    """Детали валидационной ошибки из auth-service."""

    message: str = ""
    value: Any = None # noqa: WPS110 # такое название в API


@dataclass(frozen=True)
class ResourceChangeErrorDetails:
    """Детали ошибки изменения ресурса."""

    operation: str
    detailed_error: DetailedError | None = None


@dataclass(frozen=True)
class ResourceChangeError:
    """Ошибка изменения ресурса."""

    code: str
    message: str
    details: ResourceChangeErrorDetails


@dataclass(frozen=True)
class ResourceChangeErrorResponse:
    """Ответ с ошибкой на изменение ресурса."""

    request_id: str
    status: str
    operation_result: str
    resource: ResourceRef
    error: ResourceChangeError
    meta: ResourceChangeMeta


def _serialize_api_value(raw_value: Any) -> Any:
    if isinstance(raw_value, Enum):
        serialized = raw_value.value
    elif is_dataclass(raw_value):
        serialized = {
            field.name: _serialize_api_value(getattr(raw_value, field.name))
            for field in dataclass_fields(raw_value)
        }
    elif isinstance(raw_value, tuple):
        serialized = [_serialize_api_value(element) for element in raw_value]
    elif isinstance(raw_value, list):
        serialized = [_serialize_api_value(element) for element in raw_value]
    elif isinstance(raw_value, dict):
        serialized = {
            key: _serialize_api_value(nested_value)
            for key, nested_value in raw_value.items()
        }
    else:
        serialized = raw_value
    return serialized


def to_api_dict(dataclass_instance: Any) -> dict[str, Any]:
    """Сериализует dataclass ответа API в dict, совместимый с response.json()."""
    serialized = _serialize_api_value(dataclass_instance)
    if not isinstance(serialized, dict):
        raise TypeError(f"Expected dataclass, got {type(dataclass_instance)}")
    if "operation_result" in serialized:
        serialized["result"] = serialized.pop("operation_result")
    return serialized


def assert_api_response(
    actual: dict[str, Any],
    expected: ResourceChangeResponse | ResourceChangeErrorResponse,
) -> None:
    """Сверяет весь ответ. ID применённой модели динамический и должен быть ULID."""
    expected_body = to_api_dict(expected)
    model_id = actual[META_KEY]["auth_model_id"]
    if isinstance(expected, ResourceChangeResponse):
        assert isinstance(model_id, str) and re.fullmatch(r"[0-7][0-9A-HJKMNP-TV-Z]{25}", model_id)
        empty_resource = {"id": "00000000-0000-0000-0000-000000000000", "type": "", "attributes": None}
        expected_body[META_KEY].update({
            "subject": {**empty_resource, "relation": ""},
            "resource": empty_resource,
            "action": {"name": "", "attributes": None},
            "context": {"source_service": "", "event_type": "", "trace_id": ""},
        })
    else:
        assert isinstance(model_id, str)
        assert not model_id or re.fullmatch(r"[0-7][0-9A-HJKMNP-TV-Z]{25}", model_id)
    if expected.meta.auth_model_id is not None:
        assert model_id == expected.meta.auth_model_id
    expected_body[META_KEY]["auth_model_id"] = model_id
    assert actual == expected_body
