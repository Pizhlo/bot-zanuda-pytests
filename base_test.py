"""
Базовый класс для всех тестов
"""
import pytest
import allure
from typing import Dict, Any

from utils.api_client import APIClient
from utils.helpers import generate_test_data, create_test_user_data
from config.services import webserver_config as config


class BaseTest:
    """Базовый класс для всех тестов"""
    
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.api_client = APIClient()
        self.test_data = generate_test_data()
        self.user_data = create_test_user_data()
        
        # Ждем готовности сервиса
        if not self.api_client.wait_for_service():
            pytest.skip("Service is not available")
    
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
    
    def setup_class(self):
        """Настройка перед всеми тестами в классе"""
        allure.dynamic.suite(self.__class__.__name__)
        allure.dynamic.feature("Integration Tests")
    
    def teardown_class(self):
        """Очистка после всех тестов в классе"""
        pass
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        allure.dynamic.story(self._testMethodName if hasattr(self, '_testMethodName') else 'Test')
    
    def teardown_method(self):
        """Очистка после каждого теста"""
        pass


class APITest(BaseTest):
    """Базовый класс для API тестов"""
    
    def setup_class(self):
        """Настройка для API тестов"""
        super().setup_class()
        allure.dynamic.feature("API Integration Tests")
    
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


class DatabaseTest(BaseTest):
    """Базовый класс для тестов с базой данных"""
    
    def setup_class(self):
        """Настройка для тестов БД"""
        super().setup_class()
        allure.dynamic.feature("Database Integration Tests")
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        super().setup_method()
        # Здесь можно добавить настройку тестовой БД
        pass
    
    def teardown_method(self):
        """Очистка после каждого теста"""
        # Здесь можно добавить очистку тестовой БД
        super().teardown_method()
