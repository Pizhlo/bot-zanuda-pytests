"""Чтение новых строк штатного контейнера из временного read-only файла стенда."""

import os
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

POLL_SECONDS = 0.05


@dataclass(frozen=True)
class ServiceLog:
    """Снимок позиции до запроса исключает события предыдущих тестов."""

    path: Path
    offset: int

    @classmethod
    def start(cls, path: str) -> "ServiceLog":
        source = Path(path)
        return cls(source, source.stat().st_size)

    def read(self) -> str:
        """Читает только полные строки после начала теста."""
        with self.path.open("rb") as stream:
            stream.seek(self.offset)
            return stream.read().decode(errors="replace").rpartition("\n")[0]

    def wait(self, request_id: str, message: str, count: int = 1) -> str:
        """Ждёт только строки нужной попытки. Не выводит необработанный журнал в отчёт."""
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            complete = self.read()
            if (
                sum(
                    request_id in line and message in line
                    for line in complete.splitlines()
                )
                >= count
            ):
                return complete
            time.sleep(POLL_SECONDS)
        pytest.fail(f"Не найдено {count} сообщений {message} для запроса {request_id}")

    def assert_warning(self, correlation: str) -> None:
        """Проверяет UUID раннего отказа именно в warning сервера."""
        message = "decision request failed"
        lines = self.wait(correlation, message).splitlines()
        assert any(
            correlation in line and message in line and "level=warning" in line
            for line in lines
        )


@pytest.fixture()
def service_log() -> ServiceLog | None:
    """IDE и прежний API-стенд выполняют HTTP-проверки без наблюдателя stdout."""
    path = os.environ.get("AUTH_SERVICE_LOG")
    return ServiceLog.start(path) if path else None
