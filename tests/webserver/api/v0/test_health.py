"""
Тесты для проверки здоровья веб-сервера
"""

import httpx

from src.api_clients.webserver import WebServerV0APIClient


class TestWebServerV0Health:
    """Тесты для проверки здоровья веб-сервера"""

    def test_health(self, webserver_v0_api_client: WebServerV0APIClient) -> None:
        response = webserver_v0_api_client.get_health()
        assert response.status_code == httpx.codes.OK
