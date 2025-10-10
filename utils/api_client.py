"""
API клиент для тестов
"""
import requests
import json
import time
from typing import Dict, Any, Optional, Union
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import allure

from config.services import webserver_config as config


class APIClient:
    """Клиент для работы с API"""
    
    def __init__(self, base_url: str = None, timeout: int = None):
        self.base_url = base_url or config.api_url
        self.timeout = timeout or config.TIMEOUT
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Создает сессию с настройками retry"""
        session = requests.Session()
        
        # Настройка retry стратегии
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Устанавливаем заголовки по умолчанию
        session.headers.update(config.headers)
        
        return session
    
    def _log_request(self, method: str, url: str, **kwargs):
        """Логирует запрос для Allure"""
        with allure.step(f"{method.upper()} {url}"):
            allure.attach(
                json.dumps(kwargs.get('json', {}), indent=2, ensure_ascii=False),
                name="Request Body",
                attachment_type=allure.attachment_type.JSON
            )
    
    def _log_response(self, response: requests.Response):
        """Логирует ответ для Allure"""
        try:
            response_json = response.json()
            allure.attach(
                json.dumps(response_json, indent=2, ensure_ascii=False),
                name="Response Body",
                attachment_type=allure.attachment_type.JSON
            )
        except (ValueError, json.JSONDecodeError):
            allure.attach(
                response.text,
                name="Response Body",
                attachment_type=allure.attachment_type.TEXT
            )
        
        allure.attach(
            f"Status Code: {response.status_code}",
            name="Response Status",
            attachment_type=allure.attachment_type.TEXT
        )
    
    def request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Выполняет HTTP запрос"""
        url = f"{self.base_url}{endpoint}"
        
        # Устанавливаем timeout если не указан
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        
        # Логируем запрос
        self._log_request(method, url, **kwargs)
        
        # Выполняем запрос
        response = self.session.request(method, url, **kwargs)
        
        # Логируем ответ
        self._log_response(response)
        
        return response
    
    def get(self, endpoint: str, **kwargs) -> requests.Response:
        """GET запрос"""
        return self.request('GET', endpoint, **kwargs)
    
    def post(self, endpoint: str, **kwargs) -> requests.Response:
        """POST запрос"""
        return self.request('POST', endpoint, **kwargs)
    
    def put(self, endpoint: str, **kwargs) -> requests.Response:
        """PUT запрос"""
        return self.request('PUT', endpoint, **kwargs)
    
    def patch(self, endpoint: str, **kwargs) -> requests.Response:
        """PATCH запрос"""
        return self.request('PATCH', endpoint, **kwargs)
    
    def delete(self, endpoint: str, **kwargs) -> requests.Response:
        """DELETE запрос"""
        return self.request('DELETE', endpoint, **kwargs)
    
    def wait_for_service(self, endpoint: str = "/health", max_attempts: int = 30, delay: int = 1) -> bool:
        """Ожидает готовности сервиса"""
        for attempt in range(max_attempts):
            try:
                response = self.get(endpoint)
                if response.status_code == 200:
                    return True
            except requests.RequestException:
                pass
            
            time.sleep(delay)
        
        return False
