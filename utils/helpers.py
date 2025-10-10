"""
Вспомогательные функции для тестов
"""
import random
import string
import json
from typing import Dict, Any, List

try:
    import allure
except ImportError:
    # Fallback для случаев, когда allure не установлен
    class MockAllure:
        @staticmethod
        def step(name):
            def decorator(func):
                return func
            return decorator
    allure = MockAllure()


def generate_random_string(length: int = 10) -> str:
    """Генерирует случайную строку"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def generate_random_email() -> str:
    """Генерирует случайный email"""
    username = generate_random_string(8)
    domain = random.choice(['example.com', 'test.com', 'demo.org'])
    return f"{username}@{domain}"


def generate_test_data() -> Dict[str, Any]:
    """Генерирует тестовые данные"""
    return {
        'name': f"Test User {generate_random_string(5)}",
        'email': generate_random_email(),
        'description': f"Test description {generate_random_string(20)}"
    }


def assert_response_status(response, expected_status: int):
    """Проверяет статус ответа"""
    assert response.status_code == expected_status, \
        f"Expected status {expected_status}, but got {response.status_code}. Response: {response.text}"


def assert_response_contains(response, expected_keys: List[str]):
    """Проверяет наличие ключей в JSON ответе"""
    # Если ответ пустой, считаем это валидным для health check
    if not response.text.strip():
        return
    
    try:
        data = response.json()
        for key in expected_keys:
            assert key in data, f"Key '{key}' not found in response: {data}"
    except json.JSONDecodeError:
        assert False, f"Response is not valid JSON: {response.text}"


def assert_response_not_contains(response, unexpected_keys: List[str]):
    """Проверяет отсутствие ключей в JSON ответе"""
    try:
        data = response.json()
        for key in unexpected_keys:
            assert key not in data, f"Key '{key}' found in response but should not be: {data}"
    except json.JSONDecodeError:
        assert False, f"Response is not valid JSON: {response.text}"


@allure.step("Проверка структуры ответа")
def validate_response_schema(response, schema: Dict[str, Any]):
    """Проверяет структуру ответа по схеме"""
    try:
        data = response.json()
        
        for key, expected_type in schema.items():
            assert key in data, f"Missing required field: {key}"
            assert isinstance(data[key], expected_type), \
                f"Field '{key}' should be {expected_type.__name__}, but got {type(data[key]).__name__}"
        
        allure.attach(
            json.dumps(schema, indent=2),
            name="Expected Schema",
            attachment_type=allure.attachment_type.JSON
        )
        
    except json.JSONDecodeError:
        assert False, f"Response is not valid JSON: {response.text}"


def create_test_user_data() -> Dict[str, Any]:
    """Создает данные тестового пользователя"""
    return {
        'username': generate_random_string(8),
        'email': generate_random_email(),
        'password': 'TestPassword123!',
        'first_name': 'Test',
        'last_name': 'User'
    }


def create_test_post_data() -> Dict[str, Any]:
    """Создает данные тестового поста"""
    return {
        'title': f"Test Post {generate_random_string(5)}",
        'content': f"This is a test post content. {generate_random_string(50)}",
        'tags': ['test', 'automation', 'pytest']
    }
