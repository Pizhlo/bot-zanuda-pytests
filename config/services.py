"""
Конфигурация для веб-сервера
"""
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


class WebServerConfig:
    """Конфигурация для веб-сервера"""
    
    def __init__(self):
        self.service_name = "webserver"
        self.base_url = os.getenv('WEBSERVER_URL', 'http://localhost:8080')
        self.api_version = os.getenv('WEBSERVER_API_VERSION', 'v1')
        self.timeout = int(os.getenv('WEBSERVER_TIMEOUT', '30'))
        self.api_key = os.getenv('WEBSERVER_API_KEY', '')
    
    @property
    def api_url(self) -> str:
        """Полный URL для API"""
        return f"{self.base_url}/api/{self.api_version}"
    
    @property
    def headers(self) -> dict:
        """Заголовки по умолчанию для запросов"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        return headers


# Глобальный экземпляр конфигурации веб-сервера
webserver_config = WebServerConfig()
