"""
Глобальные фикстуры и настройки pytest
"""
import pytest
import allure
import os
from datetime import datetime


def pytest_configure(config):
    """Конфигурация pytest"""
    # Создаем директорию для результатов Allure
    allure_dir = "allure-results"
    if not os.path.exists(allure_dir):
        os.makedirs(allure_dir)


def pytest_collection_modifyitems(config, items):
    """Модификация собранных тестов"""
    # Добавляем маркеры по умолчанию
    for item in items:
        # Если тест не имеет маркеров, добавляем integration
        if not any(marker.name in ['smoke', 'regression', 'integration'] for marker in item.iter_markers()):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session", autouse=True)
def setup_allure_environment():
    """Настройка окружения для Allure"""
    # Устанавливаем переменные окружения для Allure
    os.environ['ALLURE_RESULTS_DIR'] = 'allure-results'
    
    # Создаем environment.properties для Allure
    from config import config
    env_properties = {
        'Test Environment': 'Integration Tests',
        'Base URL': config.BASE_URL,
        'Test Run': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'Python Version': f'{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}'
    }
    
    with open('allure-results/environment.properties', 'w') as f:
        for key, value in env_properties.items():
            f.write(f'{key}={value}\n')


@pytest.fixture(autouse=True)
def allure_environment_info():
    """Добавляет информацию об окружении в Allure"""
    yield
    # Добавляем информацию о тесте в Allure
    from config import config
    allure.dynamic.label("test_type", "integration")
    allure.dynamic.label("base_url", config.BASE_URL)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Создает отчет о выполнении теста"""
    outcome = yield
    rep = outcome.get_result()
    
    # Добавляем скриншоты при ошибках (если нужно)
    if rep.when == "call" and rep.failed:
        # Здесь можно добавить логику для создания скриншотов
        pass


@pytest.fixture(scope="function")
def test_data():
    """Фикстура для тестовых данных"""
    return {
        'timestamp': datetime.now().isoformat(),
        'test_id': f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    }


@pytest.fixture(scope="session")
def api_base_url():
    """Фикстура для базового URL API"""
    from config import config
    return config.api_url


# Фикстуры для различных типов тестов
@pytest.fixture
def smoke_test():
    """Маркер для smoke тестов"""
    return pytest.mark.smoke


@pytest.fixture
def regression_test():
    """Маркер для regression тестов"""
    return pytest.mark.regression


@pytest.fixture
def integration_test():
    """Маркер для integration тестов"""
    return pytest.mark.integration
