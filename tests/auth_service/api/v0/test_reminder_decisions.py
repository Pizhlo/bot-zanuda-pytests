"""Остановка напоминаний в общем и личном пространствах."""

import pytest

from assertions.record_decisions import assert_record_access
from parameters.auth_service import record_decisions as cases
from src.common import fields
from src.models.decision import Actor, Role
from tests.fixtures.decision_records import Records
from tests.fixtures.decisions import DecisionClient


@pytest.mark.parametrize(
    "records", [fields.ResourceType.REMINDER], indirect=True, scope="module"
)
@pytest.mark.parametrize("case", cases.STOP_REMINDER_CASES, ids=str)
def test_stop_reminder(
    case: cases.RecordCase,
    actors: dict[Role, Actor],
    records: Records,
    decisions: DecisionClient,
) -> None:
    """Проверяет право остановить напоминание по его автору и сохранённому родительскому пространству.

    В общем пространстве остановка разрешена автору, владельцу, администратору и редактору.
    В личном пространстве это право есть только у владельца. Подмена родителя в запросе не даёт доступа.
    При двух родителях остановка возможна только для их общего владельца.
    """
    actor = actors[case.actor]
    body = records.request(case, actor)
    response = decisions.check_single_action(actor, body)
    assert_record_access(response, body, case)
