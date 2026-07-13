from typing import Any

from httpx import Response

from src.api_clients.base import APIClient
from src.config import config

HEADERS_KEY = "headers"
JSON_KEY = "json"
X_TELEGRAM_USER_ID_KEY = "X-Telegram-User-Id"
AUTHORIZATION_KEY = "Authorization"

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

    def filter_notes(self, 
    token: str | None = None, 
    body: dict | None = None, 
    x_telegram_user_id: str | None = None) -> Response:
        """
        Фильтрует заметки по заданным параметрам.
        """

        kwargs: dict = {HEADERS_KEY: {}}

        if token is not None:
            kwargs[HEADERS_KEY][AUTHORIZATION_KEY] = f"Bearer {token}"

        if x_telegram_user_id is not None:
            kwargs[HEADERS_KEY][X_TELEGRAM_USER_ID_KEY] = x_telegram_user_id

        if body is not None:
            kwargs[JSON_KEY] = body
        return self.client.post("/api/v0/auth/notes/filter", **kwargs)

    def login(self, req: dict[str, Any] | None) -> Response:
        return self.client.post("/api/v0/auth/login", json=req)

    def update_resource(
        self,
        req: dict[str, Any] | None,
        token: str | None = None,
        x_telegram_user_id: str | None = None
    ) -> Response:
        kwargs: dict = {HEADERS_KEY: {}}

        if token is not None:
            kwargs[HEADERS_KEY][AUTHORIZATION_KEY] = f"Bearer {token}"

        if req is not None:
            kwargs[JSON_KEY] = req
        
        if x_telegram_user_id is not None:
            kwargs[HEADERS_KEY][X_TELEGRAM_USER_ID_KEY] = x_telegram_user_id

        return self.client.post("/api/v0/resources/update", **kwargs)
