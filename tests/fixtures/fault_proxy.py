"""Кратковременный обрыв одного TCP-маршрута в изолированном Compose-проекте."""

import os
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager

import httpx


@contextmanager
def disconnected(name: str) -> Iterator[None]:
    """Восстанавливает доступность маршрута даже после ошибки запроса или проверки."""
    with httpx.Client(base_url=os.environ["AUTH_PROXY_API"]) as control:
        route = f"/proxies/{name}"
        with ExitStack() as cleanup:
            cleanup.callback(enable_proxy, control, route)
            control.post(route, json={"enabled": False}).raise_for_status()
            yield


def enable_proxy(control: httpx.Client, route: str) -> None:
    """Проверяет успешное восстановление подключения у тестируемого сервиса."""
    control.post(route, json={"enabled": True}).raise_for_status()
