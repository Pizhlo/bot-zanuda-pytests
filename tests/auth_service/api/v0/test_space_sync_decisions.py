"""Согласованность решений с произошедшей синхронизацией пространств."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest

from assertions.space_sync import (
    assert_personal_slot,
    assert_space_conflict,
    assert_space_read,
)
from src.models.decision import Actor, Role
from src.models.space import SpaceType
from tests.fixtures.decision_spaces import SpaceWriter
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.openfga import resource_tuple_keys
from tests.fixtures.rabbitmq import QueueMessage


def test_first_personal_space(  # noqa: WPS210 — проверки до и после записи
    writer: SpaceWriter,
    decisions: DecisionClient,
    openfga: httpx.Client,
    auth_service_error_messages_from_rabbitmq: QueueMessage,
) -> None:
    """Проверяет, когда пользователь утрачивает право создать ещё одно личное пространство.

    Пока запись не синхронизирована, проверка разрешает создание каждого из двух пространств. После записи
    первого сервис отказывает в создании второго, а попытка его синхронизации возвращает 409 Conflict.
    Второе пространство остаётся без связей в OpenFGA и недоступно для чтения.
    """
    actor = writer.actors[Role.OUTSIDER]
    first, second = writer.object_ids
    assert_personal_slot(actor, decisions, first, True)
    # Предварительная проверка не резервирует UUID или право на создание.
    assert_personal_slot(actor, decisions, second, True)
    created = writer.create(actor, first, SpaceType.PERSONAL)
    assert created.status_code == httpx.codes.OK, created.text
    assert {change["relation"] for change in created.json()["written_tuples"]} == {
        "owner",
        "created",
        SpaceType.PERSONAL,
        "has_personal_space",
    }
    assert_space_relations(openfga, first, actor, SpaceType.PERSONAL)
    assert_personal_slot(actor, decisions, second, False)
    duplicate = writer.create(actor, second, SpaceType.PERSONAL)
    assert_space_conflict(duplicate, auth_service_error_messages_from_rabbitmq)
    assert not resource_tuple_keys(openfga, f"space:{second}")
    assert_space_read(actor, decisions, second, False)


def competing_creates(
    writer: SpaceWriter, attempts: list[tuple[Actor, str, SpaceType]]
) -> list[httpx.Response]:
    """Запускает обе записи через общий барьер и возвращает ответы в порядке попыток.
    По позиции ответа тест связывает HTTP-результат с конкретным пользователем и UUID.
    """
    gate = Barrier(len(attempts))

    def create(attempt: tuple[Actor, str, SpaceType]) -> httpx.Response:  # noqa: WPS430 — общий барьер этого прогона
        gate.wait(timeout=10)
        return writer.create(*attempt)

    with ThreadPoolExecutor(max_workers=len(attempts)) as pool:
        return list(pool.map(create, attempts))


def test_concurrent_personal_spaces(  # noqa: WPS210 — два исхода синхронизации
    writer: SpaceWriter,
    decisions: DecisionClient,
    openfga: httpx.Client,
    auth_service_error_messages_from_rabbitmq: QueueMessage,
) -> None:
    """Проверяет, что две одновременные синхронизации разных личных пространств одного пользователя дают одну запись.

    Для успешной попытки сохраняются владелец, тип и отметка о личном пространстве. Другая попытка получает
    409 Conflict и не оставляет связей для отклонённого UUID. Прочитать можно только созданное пространство.
    """
    actor = writer.actors[Role.OUTSIDER]
    responses = competing_creates(
        writer,
        [(actor, object_id, SpaceType.PERSONAL) for object_id in writer.object_ids],
    )
    assert sorted(response.status_code for response in responses) == [
        httpx.codes.OK,
        httpx.codes.CONFLICT,
    ]
    assert_personal_marker(openfga, actor, occupied=True)
    for object_id, response in zip(writer.object_ids, responses, strict=True):
        if response.is_success:
            assert_space_relations(openfga, object_id, actor, SpaceType.PERSONAL)
        else:
            assert_space_conflict(response, auth_service_error_messages_from_rabbitmq)
            assert not resource_tuple_keys(openfga, f"space:{object_id}")
        assert_space_read(actor, decisions, object_id, response.is_success)


@pytest.mark.parametrize("other_kind", [SpaceType.SHARED, SpaceType.PERSONAL])
def test_concurrent_space_id(  # noqa: WPS210 — два инициатора, ответы и проверка победителя
    writer: SpaceWriter,
    openfga: httpx.Client,
    other_kind: SpaceType,
    auth_service_error_messages_from_rabbitmq: QueueMessage,
) -> None:
    """Проверяет, что два пользователя не могут одновременно создать пространство с одним UUID.

    При двух общих пространствах и при сочетании общего с личным одна попытка получает 200 OK, другая — 409 Conflict.
    Граф сохраняет тип и владельца успешной попытки. Только создание личного пространства оставляет у владельца
    отметку о нём.
    """
    space_id = writer.object_ids[0]
    attempts = (
        (writer.actors[Role.EDITOR], SpaceType.SHARED),
        (writer.actors[Role.OUTSIDER], other_kind),
    )
    responses = competing_creates(
        writer, [(actor, space_id, kind) for actor, kind in attempts]
    )
    assert sorted(response.status_code for response in responses) == [
        httpx.codes.OK,
        httpx.codes.CONFLICT,
    ]
    conflict = next(
        response
        for response in responses
        if response.status_code == httpx.codes.CONFLICT
    )
    assert_space_conflict(
        conflict, auth_service_error_messages_from_rabbitmq, same_space_id=True
    )

    winner, kind = next(
        attempt
        for attempt, response in zip(attempts, responses, strict=True)
        if response.is_success
    )
    assert_space_relations(openfga, space_id, winner, kind)
    for actor, _ in attempts:
        occupied = actor == winner and kind == SpaceType.PERSONAL
        assert_personal_marker(openfga, actor, occupied)


def assert_personal_marker(openfga: httpx.Client, actor: Actor, occupied: bool) -> None:
    """Проверяет отметку на пользователе отдельно от связей на объекте пространства."""
    subject = f"user:{actor.user_id}"
    keys = resource_tuple_keys(openfga, subject)
    actual = [(key["user"], key["relation"]) for key in keys]
    expected = [(subject, "has_personal_space")] if occupied else []
    assert actual == expected
    assert all(key["object"] == subject for key in keys)
    assert all(key.get("condition") is None for key in keys)


def assert_space_relations(
    openfga: httpx.Client, space_id: str, winner: Actor, kind: SpaceType
) -> None:
    """Читает связи победившего пространства напрямую из OpenFGA.
    Сверяет конкретного владельца, тип и отметку created после завершения синхронизации.
    """
    keys = resource_tuple_keys(openfga, f"space:{space_id}")
    actual = {(key["user"], key["relation"]) for key in keys}
    assert actual == {
        (f"user:{winner.user_id}", "owner"),
        ("user:*", kind),
        ("user:*", "created"),
    }
