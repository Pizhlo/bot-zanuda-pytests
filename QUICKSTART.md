# Быстрый старт - WebServer Tests

## 1. Установка зависимостей

```bash
# Установите зависимости (Manjaro/Arch)
pip install --break-system-packages -r requirements.txt

# Установите Allure (Manjaro/Arch)
sudo pacman -S allure
```

## 2. Настройка

```bash
# Скопируйте файл конфигурации
cp env.example .env

# Отредактируйте .env файл, указав правильный BASE_URL
nano .env
```

## 3. Запуск тестов

```bash
# Запуск всех тестов
./run.sh

# Запуск только smoke тестов
./run.sh -m smoke

# Запуск с Allure отчетом
./run.sh --allure

# Или напрямую через python
/usr/bin/python3 -m pytest -m smoke
```

## 4. Использование скрипта

```bash
# Запуск всех тестов
python run_tests.py

# Запуск smoke тестов с Allure отчетом
python run_tests.py -m smoke --allure-report
```

## Структура тестов

Все тесты наследуются от базовых классов:
- `BaseWebServerTest` - базовый класс для веб-сервера
- `WebServerAPITest` - для API тестов веб-сервера
- `WebServerDatabaseTest` - для тестов с БД веб-сервера

Пример теста:
```python
class TestMyFeature(WebServerAPITest):
    @pytest.mark.smoke
    def test_my_function(self):
        response = self.api_client.get("/my-endpoint")
        self.assert_success_response(response, 200)
```
