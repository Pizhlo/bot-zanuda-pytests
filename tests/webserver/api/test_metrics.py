import httpx

from src.api_clients.webserver import WebServerAPIClient


class TestWebServerMetrics:
    """Тесты для проверки метрик веб-сервера"""

    def test_metrics(self, webserver_api_client: WebServerAPIClient) -> None:
        response = webserver_api_client.get_metrics()
        assert response.status_code == httpx.codes.OK
        assert len(response.text) > 0
