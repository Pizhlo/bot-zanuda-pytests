"""Временное право зрителя, которое тест может отозвать между двумя запросами."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from typing import Any

import httpx

from assertions.decisions import assert_decision
from src.common import fields
from src.models.decision import Actor, DecisionReasonCode
from tests.fixtures.decisions import DecisionClient, relation, seeded_relations


@contextmanager
def viewer_grant(
    openfga: httpx.Client, actor: Actor, body: dict[str, Any]
) -> Iterator[Callable[[], None]]:
    """Создаёт общее пространство с одним viewer и адресно убирает созданные связи при выходе."""
    resource = "space:{id}".format_map(body[fields.RESOURCE_FIELD])
    viewer = relation(f"user:{actor.user_id}", "viewer", resource)
    with seeded_relations(openfga, [viewer, relation("user:*", "shared", resource)]):
        yield partial(revoke_role, openfga, viewer)


def revoke_role(openfga: httpx.Client, viewer: dict[str, str]) -> None:
    """Дожидается подтверждения удаления роли от реального OpenFGA."""
    openfga.post("write", json={"deletes": {"tuple_keys": [viewer]}}).raise_for_status()


def read_before_and_after_revocation(
    decisions: DecisionClient,
    openfga: httpx.Client,
    viewer: Actor,
    body: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Дважды отправляет одно тело. Между запросами дожидается подтверждения отзыва права от OpenFGA."""
    with viewer_grant(openfga, viewer, body) as revoke:
        first = assert_decision(
            decisions.check_single_action(viewer, body),
            body,
            True,
            DecisionReasonCode.ALLOWED_VIA_FGA_RELATION,
        )
        revoke()
        second = assert_decision(
            decisions.check_single_action(viewer, body),
            body,
            False,
            DecisionReasonCode.DENIED_BY_FGA_RELATION,
        )
    return first, second
