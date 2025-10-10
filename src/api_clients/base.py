from typing import Any

import httpx


class APIClient:
    """Клиент для работы с API"""

    def __init__(self) -> None:
        self.client = httpx.Client()

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.client.get(url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.client.post(url, **kwargs)
