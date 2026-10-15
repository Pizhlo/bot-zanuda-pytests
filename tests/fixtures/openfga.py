"""Доступ к тестовому OpenFGA для очистки ресурсов без перезапуска сервиса."""

from collections.abc import Generator

import httpx
import pytest

from src.config import config


@pytest.fixture(scope="session")
def openfga() -> Generator[httpx.Client, None, None]:
    """Открывает единственное хранилище с именем из готового тестового YAML.

    Хранилище и модель создаёт auth-service. Фикстура не создаёт и не сбрасывает их;
    при неоднозначном имени останавливается, чтобы не выбрать чужое хранилище.
    Клиент закрывается после pytest. Путь клиента ограничен выбранным store.
    """
    with httpx.Client(
        base_url=str(config.openfga.base_url),
        timeout=config.openfga.timeout,
    ) as client:
        response = client.get("/stores", params={"name": config.openfga.store_name})
        response.raise_for_status()
        payload = response.json()
        stores = [
            store
            for store in payload["stores"]
            if store["name"] == config.openfga.store_name
        ]
        assert len(stores) == 1 and not payload.get("continuation_token"), (
            "Expected one test OpenFGA store"
        )
        store_id = stores[0]["id"]
        client.base_url = f"{str(config.openfga.base_url).rstrip('/')}/stores/{store_id}/"
        yield client


def remove_resource_relations(client: httpx.Client, object_ref: str) -> None:
    """Удаляет связи только уникального объекта, принадлежащего сценарию pytest.

    API auth-service пока не реализует delete, поэтому уборка идёт прямо в OpenFGA.
    Чтение с HIGHER_CONSISTENCY находит записанные только что связи; пустой результат
    допускается, если проверяемый запрос завершился ошибкой до создания ресурса.
    У сценариев создания максимум две связи. Неожиданную пагинацию считаем ошибкой,
    чтобы не выдавать частичную очистку за успешную. Базовые SQL/модель не меняются.
    """
    response = client.post(
        "read",
        json={
            "tuple_key": {"object": object_ref},
            "consistency": "HIGHER_CONSISTENCY",
        },
    )
    response.raise_for_status()
    payload = response.json()
    assert not payload.get("continuation_token"), (
        "Unexpected pagination for a test resource"
    )
    keys = [entry["key"] for entry in payload["tuples"]]
    if keys:
        response = client.post("write", json={"deletes": {"tuple_keys": keys}})
        response.raise_for_status()
