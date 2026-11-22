"""Фикстуры изолированного контейнерного стенда для операционных проверок."""

import os
from collections.abc import Iterator
from uuid import UUID

import httpx
import pytest

from src.api_clients.auth_service import AuthServiceV0APIClient
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.service_log import ServiceLog


@pytest.fixture()
def main_log(service_log: ServiceLog | None) -> ServiceLog:
    """Операционные проверки требуют временный журнал своего контейнера."""
    assert service_log is not None
    return service_log


@pytest.fixture(scope="session")
def model_id(openfga: httpx.Client) -> str:
    """Сверяет единственную строгую модель общего изолированного хранилища."""
    models = (
        openfga.get("authorization-models")
        .raise_for_status()
        .json()["authorization_models"]
    )
    assert len(models) == 1
    return str(models[0]["id"])


@pytest.fixture()
def observed_decisions(
    login: str, decision_request_ids: set[UUID]
) -> Iterator[DecisionClient]:
    """Отправляет только этот сценарий в выделенный штатный экземпляр с доставкой info."""
    api = AuthServiceV0APIClient()
    api.client.base_url = os.environ["AUTH_OBSERVED_URL"]
    with api.client:
        yield DecisionClient(api, login, decision_request_ids)
