"""
Тесты для проверки здоровья сервиса авторизации
"""

import httpx

from src.api_clients.auth_service import AuthServiceV0APIClient


class TestAuthServiceV0Health:
    """Тесты для проверки здоровья сервиса авторизации"""

    def test_health(self, auth_service_v0_api_client: AuthServiceV0APIClient) -> None:
        response = auth_service_v0_api_client.get_health()
        assert response.status_code == httpx.codes.OK