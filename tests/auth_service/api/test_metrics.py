import httpx
import logging
from src.api_clients.auth_service import AuthServiceAPIClient
from src.common.server_error_logging import log_internal_server_error
from src.common.fields import ERROR_FIELD

logger = logging.getLogger(__name__)

class TestAuthServiceMetrics:
    """Тесты для проверки метрик сервиса авторизации"""

    def test_metrics(self, auth_service_api_client: AuthServiceAPIClient) -> None:
        response = auth_service_api_client.get_metrics()
        log_internal_server_error(response, logger, ERROR_FIELD)
        assert response.status_code == httpx.codes.OK
        assert len(response.text) > 0
