from httpx import Response

from src.api_clients.base import APIClient
from src.config import config


class AuthServiceAPIClient(APIClient):
    """Клиент для работы с API сервиса авторизации"""

    def __init__(self) -> None:
        super().__init__()
        self.client.base_url = str(config.auth_service.base_url)
        self.client.timeout = config.auth_service.timeout

    def get_metrics(self) -> Response:
        return self.client.get("/metrics")

class AuthServiceV0APIClient(AuthServiceAPIClient):
    """Клиент для работы с API сервиса авторизации v0"""

    def get_health(self) -> Response:
        return self.client.get("/api/v0/health")

    def filter_notes(self, token: str | None = None, body: dict | None = None) -> Response:
        kwargs: dict = {}

        if token is not None:
            kwargs["headers"]= {"Authorization": f"Bearer {token}"}

        if body is not None:
            kwargs["json"] = body
        return self.client.post("/api/v0/auth/notes/filter", **kwargs)
