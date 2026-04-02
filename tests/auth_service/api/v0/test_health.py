"""
Тесты для проверки здоровья сервиса авторизации
"""

import httpx
import logging
from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common.server_error_logging import log_internal_server_error
from src.common.fields import ERROR_FIELD

logger = logging.getLogger(__name__)

class TestAuthServiceV0Health:
    """Тесты для проверки здоровья сервиса авторизации"""

    def test_health(self, auth_service_v0_api_client: AuthServiceV0APIClient) -> None:
        response = auth_service_v0_api_client.get_health()
        log_internal_server_error(response, logger, ERROR_FIELD)
        assert response.status_code == httpx.codes.OK