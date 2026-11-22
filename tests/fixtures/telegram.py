"""Telegram ID для временных пользователей и сценариев с неизвестной личностью."""

from collections.abc import Iterator
from secrets import randbelow

import pytest

from src.storages.postgres_client import PostgresClient

MAX_TELEGRAM_ID = 1_000_000_000_000_000


def new_telegram_id() -> str:
    """Создаёт положительный десятичный ID для текущего теста."""
    return str(randbelow(MAX_TELEGRAM_ID) + 1)


@pytest.fixture()
def unregistered_telegram(postgres_client: PostgresClient) -> Iterator[str]:
    """Выбирает свободный Telegram ID и удаляет привязку, если запрос ошибочно её создаст."""
    telegram = new_telegram_id()
    key = (int(telegram),)
    assert not postgres_client.fetch_all(
        "SELECT user_id FROM users.telegram WHERE tg_id = %s", key
    )
    try:
        yield telegram
    finally:
        postgres_client.execute("DELETE FROM users.telegram WHERE tg_id = %s", key)
