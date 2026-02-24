import httpx

from src.api_clients.auth_service import AuthServiceAPIClient


class TestAuthServiceMetrics:
    """Тесты для проверки метрик сервиса авторизации"""

    def test_metrics(self, auth_service_api_client: AuthServiceAPIClient) -> None:
        response = auth_service_api_client.get_metrics()
        assert response.status_code == httpx.codes.OK
        assert len(response.text) > 0
