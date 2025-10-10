"""
Тесты для проверки здоровья веб-сервера
"""
import pytest
import allure
from base_service_test import WebServerAPITest


class TestWebServerHealth(WebServerAPITest):
    """Тесты для проверки здоровья веб-сервера"""
    
    @allure.title("Проверка доступности веб-сервера")
    @allure.description("Проверяем, что веб-сервер отвечает на health check")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.smoke
    @pytest.mark.critical
    @pytest.mark.webserver
    def test_health_check(self):
        """Проверяет доступность веб-сервера"""
        with allure.step("Отправляем GET запрос на /health"):
            response = self.api_client.get("/health")
        
        with allure.step("Проверяем статус ответа"):
            self.assert_success_response(response, 200)
        
        with allure.step("Проверяем структуру ответа веб-сервера"):
            # Веб-сервер должен возвращать базовую информацию о здоровье
            self.assert_response_contains(response, ["status", "timestamp", "uptime"])
    
    @allure.title("Проверка метрик веб-сервера")
    @allure.description("Проверяем, что веб-сервер предоставляет метрики")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.integration
    def test_metrics_endpoint(self):
        """Проверяет endpoint с метриками"""
        # Метрики доступны по корневому пути, а не по API пути
        from config.services import webserver_config
        import requests
        
        with allure.step("Отправляем GET запрос на /metrics"):
            metrics_url = f"{webserver_config.base_url}/metrics"
            response = requests.get(metrics_url, headers=webserver_config.headers)
        
        # Если endpoint не реализован, пропускаем тест
        if response.status_code == 404:
            pytest.skip("Metrics endpoint not implemented yet")
        
        with allure.step("Проверяем статус ответа"):
            self.assert_success_response(response, 200)
        
        with allure.step("Проверяем, что ответ содержит метрики"):
            # Prometheus метрики обычно возвращаются как text/plain
            content_type = response.headers.get("content-type", "")
            assert "text/plain" in content_type or "application/json" in content_type
            assert len(response.text) > 0
