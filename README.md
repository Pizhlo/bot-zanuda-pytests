# Bot Zanuda - WebServer Integration Tests

Интеграционные тесты для веб-сервера Bot Zanuda, написанные с использованием pytest и Allure.

## Установка и настройка

### 1. Установка зависимостей

```bash
# Установите зависимости (для Manjaro/Arch Linux)
pip install --break-system-packages -r requirements.txt

# Или установите через pacman (рекомендуется)
sudo pacman -S python-pytest python-pytest-cov python-pytest-xdist python-pytest-html python-pydantic python-dotenv
```

### 2. Установка Allure

#### Linux (Manjaro/Arch):
```bash
sudo pacman -S allure
```

#### macOS:
```bash
brew install allure
```

#### Windows:
```bash
# Скачайте и установите с https://github.com/allure-framework/allure2/releases
# Или используйте Scoop:
scoop install allure
```

### 3. Настройка окружения

Создайте файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Отредактируйте `.env` файл, указав правильные значения:

```env
BASE_URL=http://localhost:8080
API_VERSION=v1
TIMEOUT=30
API_KEY=your_api_key_here
```

## Запуск тестов

### Базовые команды

```bash
# Запуск всех тестов
/usr/bin/python3 -m pytest

# Запуск с подробным выводом
/usr/bin/python3 -m pytest -v

# Запуск конкретного файла
/usr/bin/python3 -m pytest tests/test_health_check.py

# Запуск конкретного теста
/usr/bin/python3 -m pytest tests/test_health_check.py::TestHealthCheck::test_health_check

# Или используйте удобный скрипт
./run.sh                    # Запустить все тесты
./run.sh -v                 # Подробный вывод
./run.sh --help             # Справка
```

### Запуск по маркерам

```bash
# Только smoke тесты (быстрые тесты)
/usr/bin/python3 -m pytest -m smoke
# или
./run.sh -m smoke

# Только критически важные тесты
/usr/bin/python3 -m pytest -m critical
# или
./run.sh -m critical

# Интеграционные тесты
/usr/bin/python3 -m pytest -m integration

# Исключить медленные тесты
/usr/bin/python3 -m pytest -m "not slow"
```

### Параллельный запуск

```bash
# Запуск в 4 потока
pytest -n 4

# Автоматическое определение количества потоков
pytest -n auto
```

### Создание отчетов

```bash
# HTML отчет
pytest --html=report.html --self-contained-html

# Отчет с покрытием кода
pytest --cov=. --cov-report=html --cov-report=term

# Allure отчет
pytest --alluredir=allure-results
allure generate allure-results -o allure-report --clean
allure open allure-report
```

### Использование скрипта run_tests.py

```bash
# Запуск всех тестов
python run_tests.py

# Запуск smoke тестов
python run_tests.py -m smoke

# Запуск с покрытием кода
python run_tests.py -c

# Запуск в 4 потока с Allure отчетом
python run_tests.py -n 4 --allure-report

# Запуск конкретного файла
python run_tests.py -f tests/test_health_check.py
```

## Структура тестов

### Базовые классы

- `BaseTest` - базовый класс для всех тестов
- `APITest` - базовый класс для API тестов
- `DatabaseTest` - базовый класс для тестов с БД

### Пример теста

```python
import pytest
import allure
from base_test import APITest

class TestMyFeature(APITest):
    """Тесты для моей функции"""
    
    @allure.title("Проверка создания ресурса")
    @allure.description("Проверяем создание нового ресурса")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.smoke
    @pytest.mark.critical
    def test_create_resource(self):
        """Проверяет создание ресурса"""
        with allure.step("Отправляем POST запрос"):
            response = self.api_client.post("/resources", json=self.test_data)
        
        with allure.step("Проверяем статус ответа"):
            self.assert_success_response(response, 201)
        
        with allure.step("Проверяем структуру ответа"):
            self.assert_response_contains(response, ["id", "name"])
```

## Маркеры тестов

- `smoke` - быстрые тесты для проверки основной функциональности
- `regression` - полный набор тестов для регрессионного тестирования
- `integration` - интеграционные тесты
- `api` - API тесты
- `slow` - медленные тесты
- `critical` - критически важные тесты

## Конфигурация

### pytest.ini
Основные настройки pytest, включая маркеры и опции запуска.

### config.py
Конфигурация для тестов: URL сервера, таймауты, ключи API.

### allure.properties
Настройки для Allure отчетов.

## CI/CD интеграция

### GitHub Actions пример

```yaml
name: Integration Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    - name: Run tests
      run: pytest --alluredir=allure-results
    - name: Generate Allure Report
      uses: simple-elf/allure-report-action@master
      with:
        allure_results: allure-results
```

## Отладка

### Включение подробного логирования

```bash
pytest -v -s --tb=long
```

### Запуск одного теста с отладкой

```bash
pytest -v -s tests/test_health_check.py::TestHealthCheck::test_health_check --pdb
```

### Проверка конфигурации

```bash
pytest --collect-only
```

## Полезные команды

```bash
# Очистка кэша pytest
pytest --cache-clear

# Показать доступные маркеры
pytest --markers

# Показать конфигурацию
pytest --config-file

# Запуск с профилированием
pytest --profile
```

## Troubleshooting

### Проблемы с Allure

1. Убедитесь, что Allure установлен и доступен в PATH
2. Проверьте права доступа к директории allure-results
3. Очистите старые результаты: `rm -rf allure-results allure-report`

### Проблемы с подключением к серверу

1. Проверьте, что сервер запущен и доступен
2. Убедитесь, что BASE_URL в .env файле правильный
3. Проверьте настройки файрвола и сети

### Проблемы с зависимостями

1. Обновите pip: `pip install --upgrade pip`
2. Переустановите зависимости: `pip install -r requirements.txt --force-reinstall`
3. Проверьте совместимость версий Python
