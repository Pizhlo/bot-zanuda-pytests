"""Подготовка исходных связей для прямых изменений пространства."""

import httpx
import pytest

from parameters.auth_service.space_privacy import PrivacyCase
from src.common import fields
from src.models.decision import Role
from tests.fixtures.decision_spaces import SpaceWriter


@pytest.fixture()
def privacy_writer(
    case: PrivacyCase, writer: SpaceWriter, openfga: httpx.Client
) -> SpaceWriter:
    """Готовит исходный граф сценария. Родительская фикстура уже зарегистрировала уборку всех его объектов."""
    owner = writer.actors[Role.EDITOR]
    space = writer.object_ids[0]
    if case.stored:
        response = writer.create(owner, space, case.stored)
        assert response.status_code == httpx.codes.OK, response.text
    if (
        case.change == fields.ChangeType.MEMBERSHIP_CHANGED
        and case.requested is not None
    ):
        member = writer.actors[Role.OUTSIDER]
        key = {
            "user": f"user:{member.user_id}",
            "relation": "viewer",
            "object": f"space:{space}",
        }
        openfga.post("write", json={"writes": {"tuple_keys": [key]}}).raise_for_status()
    return writer
