"""
Базовый класс для тестов веб-сервера
"""
import pytest
import allure
from typing import Dict, Any

from utils.api_client import APIClient
from utils.helpers import generate_test_data, create_test_user_data
from config.services import webserver_config


class BaseWebServerTest:
    """Базовый класс для тестов веб-сервера"""
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Инициализируем конфигурацию для всех подклассов
        cls.service_name = "webserver"
        cls.service_config = webserver_config
        cls.api_client = APIClient(
            base_url=webserver_config.api_url,
            timeout=webserver_config.timeout
        )
        cls.api_client.session.headers.update(webserver_config.headers)
    
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.test_data = generate_test_data()
        self.user_data = create_test_user_data()
        
        # Ждем готовности сервиса
        if not self.api_client.wait_for_service():
            pytest.skip(f"Service {self.service_name} is not available")
    
    @pytest.fixture
    def api_client(self) -> APIClient:
        """Фикстура для API клиента"""
        return self.api_client
    
    @pytest.fixture
    def test_data(self) -> Dict[str, Any]:
        """Фикстура для тестовых данных"""
        return self.test_data
    
    @pytest.fixture
    def user_data(self) -> Dict[str, Any]:
        """Фикстура для данных пользователя"""
        return self.user_data
    
    @classmethod
    def setup_class(cls):
        """Настройка перед всеми тестами в классе"""
        allure.dynamic.suite(f"{cls.service_name.title()} Service Tests")
        allure.dynamic.feature(f"{cls.service_name.title()} Integration Tests")
    
    @classmethod
    def teardown_class(cls):
        """Очистка после всех тестов в классе"""
        pass
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        allure.dynamic.story(self._testMethodName if hasattr(self, '_testMethodName') else 'Test')
    
    def teardown_method(self):
        """Очистка после каждого теста"""
        pass


class WebServerAPITest(BaseWebServerTest):
    """Базовый класс для API тестов веб-сервера"""
    
    @classmethod
    def setup_class(cls):
        """Настройка для API тестов"""
        super().setup_class()
        allure.dynamic.feature("WebServer API Integration Tests")
    
    def assert_success_response(self, response, expected_status: int = 200):
        """Проверяет успешный ответ"""
        assert response.status_code == expected_status, \
            f"Expected status {expected_status}, but got {response.status_code}. Response: {response.text}"
    
    def assert_error_response(self, response, expected_status: int):
        """Проверяет ответ с ошибкой"""
        assert response.status_code == expected_status, \
            f"Expected error status {expected_status}, but got {response.status_code}. Response: {response.text}"
    
    def assert_response_contains(self, response, expected_keys: list):
        """Проверяет наличие ключей в ответе"""
        from utils.helpers import assert_response_contains
        assert_response_contains(response, expected_keys)
    
    def assert_response_not_contains(self, response, unexpected_keys: list):
        """Проверяет отсутствие ключей в ответе"""
        from utils.helpers import assert_response_not_contains
        assert_response_not_contains(response, unexpected_keys)


class WebServerDatabaseTest(BaseWebServerTest):
    """Базовый класс для тестов с базой данных веб-сервера"""
    
    @classmethod
    def setup_class(cls):
        """Настройка для тестов БД"""
        super().setup_class()
        allure.dynamic.feature("WebServer Database Integration Tests")
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        super().setup_method()
        # Здесь можно добавить настройку тестовой БД
        pass
    
    def teardown_method(self):
        """Очистка после каждого теста"""
        # Здесь можно добавить очистку тестовой БД
        super().teardown_method()
