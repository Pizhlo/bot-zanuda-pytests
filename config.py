"""
Конфигурация для тестов
"""
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

class Config:
    """Конфигурация для тестов"""
    
    # Базовые настройки
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:8080')
    API_VERSION = os.getenv('API_VERSION', 'v1')
    TIMEOUT = int(os.getenv('TIMEOUT', '30'))
    
    # Аутентификация
    API_KEY = os.getenv('API_KEY', '')
    USERNAME = os.getenv('USERNAME', '')
    PASSWORD = os.getenv('PASSWORD', '')
    
    # Настройки для отчетов
    ALLURE_RESULTS_DIR = os.getenv('ALLURE_RESULTS_DIR', 'allure-results')
    ALLURE_REPORT_DIR = os.getenv('ALLURE_REPORT_DIR', 'allure-report')
    
    @property
    def api_url(self) -> str:
        """Полный URL для API"""
        return f"{self.BASE_URL}/api/{self.API_VERSION}"
    
    @property
    def headers(self) -> dict:
        """Заголовки по умолчанию для запросов"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        if self.API_KEY:
            headers['Authorization'] = f'Bearer {self.API_KEY}'
        return headers

# Глобальный экземпляр конфигурации
config = Config()
