"""Проверки опубликованных сообщений webserver."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.models.models import FullMessage


def assert_note_message(message: bytes | None, expected: FullMessage) -> None:
    """Сравнивает payload и проверяет время создания с допуском две секунды."""
    if not message:
        pytest.fail("Нет сообщений")
    actual = FullMessage.model_validate_json(message)
    expected.created = actual.created
    assert actual == expected
    moscow_tz = ZoneInfo("Europe/Moscow")
    message_time = get_message_time(actual, moscow_tz)
    current_time = datetime.now(moscow_tz)
    check_time_difference(message_time, current_time, 2)


def check_time_difference(
    message_time: datetime, current_time: datetime, max_allowed_diff: int = 2
) -> None:
    """
    Проверяет разницу между временем создания операции и текущим временем.
    По умолчанию максимальная разница 2 секунды.
    """
    time_diff = abs((current_time - message_time).total_seconds())
    assert time_diff <= max_allowed_diff, (
        f"Time difference {time_diff}s exceeds allowed {max_allowed_diff}s"
    )


def get_message_time(message: FullMessage, tz: ZoneInfo) -> datetime:
    """
    Получает время создания операции из поля created
    """
    if message.created is not None:
        return datetime.fromtimestamp(message.created, tz=tz)

    pytest.fail("Message created timestamp is None")
