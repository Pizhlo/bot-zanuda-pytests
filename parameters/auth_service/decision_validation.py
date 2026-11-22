"""Операции, параметры согласованности и ошибки атрибутов решений."""

from itertools import product
from uuid import uuid4

import pytest

from parameters.auth_service import decisions as decision_params
from src.common import fields
from src.models.decision import Consistency, DecisionReasonCode
from src.models.space import SpaceType

VALIDATE_REQUEST = "validate_request"

SUPPORTED = (
    (
        fields.ResourceType.SPACE,
        (
            fields.Operation.CREATE,
            decision_params.READ,
            fields.Operation.UPDATE,
            fields.Operation.DELETE,
        ),
    ),
    (
        fields.ResourceType.NOTE,
        (
            fields.Operation.CREATE,
            decision_params.READ,
            fields.Operation.UPDATE,
            fields.Operation.DELETE,
        ),
    ),
    (
        fields.ResourceType.REMINDER,
        (
            fields.Operation.CREATE,
            decision_params.READ,
            fields.Operation.UPDATE,
            fields.Operation.DELETE,
            decision_params.STOP,
        ),
    ),
    (
        decision_params.MEMBER,
        (decision_params.ADD, decision_params.EDIT, decision_params.REMOVE),
    ),
)
ALL_ACTIONS = (
    fields.Operation.CREATE,
    decision_params.READ,
    fields.Operation.UPDATE,
    fields.Operation.DELETE,
    decision_params.STOP,
    decision_params.ADD,
    decision_params.EDIT,
    decision_params.REMOVE,
)


UNSUPPORTED_ACTION_CASES = tuple(
    (kind, action)
    for (kind, supported), action in product(SUPPORTED, ALL_ACTIONS)
    if action not in supported
)
"""Проверка недопустимых сочетаний ресурса и действия.

- Для space или note запрошено stop, add, edit либо remove: 400 Bad Request.
- Для reminder запрошено add, edit либо remove: 400 Bad Request.
- Для member запрошено create, read, update, delete либо stop: 400 Bad Request.

Во всех случаях invalid_request указывает на action.name. В ответе нет decision_id.
"""


INVALID_ATTRIBUTE_CASES = (
    pytest.param(
        fields.ResourceType.NOTE,
        fields.Operation.CREATE,
        {},
        {},
        "resource.attributes.space_id is required for note/reminder create and member actions",
        VALIDATE_REQUEST,
        id="note-without-space",
    ),
    pytest.param(
        fields.ResourceType.REMINDER,
        fields.Operation.CREATE,
        {},
        {},
        "resource.attributes.space_id is required for note/reminder create and member actions",
        VALIDATE_REQUEST,
        id="reminder-without-space",
    ),
    pytest.param(
        decision_params.MEMBER,
        decision_params.REMOVE,
        {},
        {},
        "resource.attributes.space_id is required for note/reminder create and member actions",
        VALIDATE_REQUEST,
        id="member-without-space",
    ),
    pytest.param(
        fields.ResourceType.SPACE,
        fields.Operation.CREATE,
        {},
        {},
        "resource.attributes.space_type is required for space:create",
        VALIDATE_REQUEST,
        id="space-without-kind",
    ),
    pytest.param(
        fields.ResourceType.SPACE,
        fields.Operation.CREATE,
        {},
        {fields.SPACE_TYPE_FIELD: "private"},
        "resource.attributes.space_type must be shared or personal",
        VALIDATE_REQUEST,
        id="unknown-space-kind",
    ),
    pytest.param(
        fields.ResourceType.SPACE,
        decision_params.READ,
        {},
        {fields.SPACE_TYPE_FIELD: SpaceType.PERSONAL},
        "resource.attributes.space_type is only supported for space:create",
        VALIDATE_REQUEST,
        id="kind-on-space-read",
    ),
    pytest.param(
        fields.ResourceType.NOTE,
        decision_params.READ,
        {},
        {fields.SPACE_TYPE_FIELD: SpaceType.SHARED},
        "resource.attributes.space_type is only supported for space:create",
        VALIDATE_REQUEST,
        id="kind-on-note-read",
    ),
    pytest.param(
        fields.ResourceType.SPACE,
        fields.Operation.DELETE,
        {},
        {fields.SPACE_ID_FIELD: str(uuid4())},
        "resource.attributes.space_id must be a nonzero UUID and is not supported for space resources",
        VALIDATE_REQUEST,
        id="parent-on-space-delete",
    ),
    pytest.param(
        fields.ResourceType.NOTE,
        fields.Operation.UPDATE,
        {},
        {},
        "action.attributes.field_mask must be nonempty for update",
        VALIDATE_REQUEST,
        id="missing-mask",
    ),
    pytest.param(
        fields.ResourceType.REMINDER,
        fields.Operation.UPDATE,
        {fields.FIELD_MASK_FIELD: []},
        {},
        "action.attributes.field_mask must be nonempty for update",
        VALIDATE_REQUEST,
        id="empty-mask",
    ),
    pytest.param(
        fields.ResourceType.SPACE,
        fields.Operation.UPDATE,
        {fields.FIELD_MASK_FIELD: [""]},
        {},
        "action.attributes.field_mask must contain nonempty field names",
        "decode_request",
        id="empty-field",
    ),
    pytest.param(
        fields.ResourceType.NOTE,
        decision_params.READ,
        {fields.FIELD_MASK_FIELD: [fields.TITLE_FIELD]},
        {},
        "action.attributes.field_mask is only supported for update",
        VALIDATE_REQUEST,
        id="mask-on-read",
    ),
    pytest.param(
        fields.ResourceType.REMINDER,
        decision_params.STOP,
        {fields.FIELD_MASK_FIELD: [fields.TITLE_FIELD]},
        {},
        "action.attributes.field_mask is only supported for update",
        VALIDATE_REQUEST,
        id="mask-on-stop",
    ),
    pytest.param(
        fields.ResourceType.SPACE,
        decision_params.READ,
        {fields.ROLE_FIELD: "viewer"},
        {},
        "action.attributes.role is only supported for member add/edit",
        VALIDATE_REQUEST,
        id="role-on-read",
    ),
    pytest.param(
        fields.ResourceType.NOTE,
        fields.Operation.CREATE,
        {},
        {"members": [], fields.SPACE_ID_FIELD: str(uuid4())},
        "resource.attributes contains an unknown field",
        "decode_request",
        id="members-on-note-create",
    ),
)
"""Валидация обязательных и лишних атрибутов до проверки полномочий.

- Создание заметки или напоминания без space_id: 400 Bad Request.
- Удаление участника без space_id: 400 Bad Request.
- Создание пространства без space_type или с неизвестным значением private: 400 Bad Request.
- При чтении пространства передан space_type=personal: 400 Bad Request.
- При чтении заметки передан space_type=shared: 400 Bad Request.
- При удалении пространства передан лишний space_id: 400 Bad Request.
- Обновление заметки без field_mask: 400 Bad Request.
- Обновление напоминания с пустым списком field_mask: 400 Bad Request.
- Обновление пространства с пустой строкой в field_mask: 400 Bad Request.
- Чтение заметки или остановка напоминания с field_mask из одного поля title: 400 Bad Request.
- При чтении пространства передан role=viewer: 400 Bad Request.
- При создании заметки переданы members вместе с корректным space_id: 400 Bad Request.

Сверяем путь к ошибочному атрибуту в invalid_request и request_id. В ответе нет decision_id.
"""


DECISION_OPTION_CASES = (
    pytest.param(
        {
            fields.INCLUDE_REASONS_FIELD: False,
            fields.CONSISTENCY_FIELD: Consistency.HIGHER_CONSISTENCY,
        },
        (),
        id="consistent-without-reasons",
    ),
    pytest.param(
        {
            fields.INCLUDE_REASONS_FIELD: True,
            fields.CONSISTENCY_FIELD: Consistency.MINIMIZE_LATENCY,
        },
        (DecisionReasonCode.ALLOWED_FOR_REGISTERED_USER,),
        id="low-latency-with-reasons",
    ),
)
"""Редактор запрашивает создание общего пространства с разными параметрами ответа.

- higher_consistency и include_reasons=false: 200 OK, allow без объяснения.
- minimize_latency и include_reasons=true: 200 OK, allow с причиной allowed_for_registered_user.
"""
