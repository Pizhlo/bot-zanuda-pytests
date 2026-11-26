"""Проверка полномочий на update сохраняет решение и оставляет бизнес-данные заметки неизменными."""

import httpx

from assertions.decisions import assert_decision
from src.common import fields
from src.models.decision import Actor, DecisionReasonCode, Role, decision_request
from src.storages.postgres_client import PostgresClient
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.openfga import resource_tuple_keys


def note_state(
    postgres: PostgresClient, openfga: httpx.Client, note: str
) -> tuple[object, ...]:
    """Читает все колонки и полные связи заметки, упорядоченные для сравнения снимков."""
    row = postgres.fetch_one("SELECT * FROM notes.notes WHERE id = %s", (note,))
    assert row is not None
    graph = sorted(
        resource_tuple_keys(openfga, f"note:{note}"), key=lambda key: key["relation"]
    )
    return row, graph


def test_check_leaves_note_unchanged(
    stored_note: str,
    actors: dict[Role, Actor],
    openfga: httpx.Client,
    postgres_client: PostgresClient,
    decisions: DecisionClient,
) -> None:
    """Проверяет, что разрешение на изменение заголовка заметки само по себе не изменяет заметку.

    Владелец получает разрешение, а все поля сохранённой заметки и её связи в OpenFGA остаются прежними.
    """
    owner = actors[Role.OWNER]
    body = decision_request(
        owner,
        fields.Operation.UPDATE,
        fields.ResourceType.NOTE,
        stored_note,
        action_attributes={fields.FIELD_MASK_FIELD: [fields.TITLE_FIELD]},
    )
    before = note_state(postgres_client, openfga, stored_note)
    assert_decision(
        decisions.check_single_action(owner, body),
        body,
        True,
        DecisionReasonCode.ALLOWED_VIA_FGA_RELATION,
        DecisionReasonCode.ALLOWED_FIELDS,
    )
    assert note_state(postgres_client, openfga, stored_note) == before
