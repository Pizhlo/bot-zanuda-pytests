from httpx import Response

from src.api_clients.base import APIClient
from src.config import config


class WebServerAPIClient(APIClient):
    """Клиент для работы с API веб-сервера"""

    def __init__(self) -> None:
        super().__init__()
        self.client.base_url = str(config.webserver.base_url)
        self.client.timeout = config.webserver.timeout

    def get_metrics(self) -> Response:
        return self.client.get("/metrics")


class WebServerV0APIClient(WebServerAPIClient):
    """Клиент для работы с API веб-сервера v0"""

    def get_health(self) -> Response:
        return self.client.get("/api/v0/health")

    def create_note(self, note: dict) -> Response:
        return self.client.post(
            "/api/v0/spaces/notes/create",
            json=note,
        )
