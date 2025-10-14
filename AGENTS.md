# Agent Context

## Tech Stack
- Python 3.13+
- pytest 8.4+
- uv (package manager)
- Docker & Docker Compose
- Make (build system)
- mypy for type checking
- flake8, ruff for linting

## Key Commands
```bash
make install          # install uv and sync dependencies
make lint             # run flake8, ruff check, mypy
make fix              # format code with ruff, fix imports
make start-containers # start test environment (db, rabbitmq, vault)
make test             # run all tests
make test-auth-service # run only auth service tests
make stop-containers  # stop test environment
make restart-containers # restart test environment
make clean-containers # stop and remove containers
make docker-build     # build Docker image
make docker-push      # push Docker image to registry
make docker-login     # login to Docker registry
```

## Project Structure
- `src/` — test utilities and API clients
  - `src/api_clients/` — HTTP clients for tested services
  - `src/models/` — data models for tests
  - `src/databases/` — database clients
  - `src/brokers/` — RabbitMQ client
  - `src/storages/` — Vault client
- `tests/` — actual test files
  - `tests/auth_service/` — auth service API tests
  - `tests/webserver/` — web server API tests
  - `tests/fixtures/` — pytest fixtures (JWT, db, rabbitmq, vault)
  - `tests/conftest.py` — global pytest configuration
- `scripts/` — setup scripts (rabbitmq-setup.sh)

## Architecture Context
- End-to-end tests for entire project (web server, auth service, bot)
- Currently testing: web server and auth service
- Future: bot tests
- Auth-service environments use the pinned testkit (container or Linux host modes)
- Each test suite has its own database schema

## Test Patterns
- Use fixtures from `tests/fixtures/` for setup (JWT, db, rabbitmq)
- Use API clients from `src/api_clients/` for HTTP requests
- Use models from `src/models/` for request/response validation
- All tests MUST be independent (no order dependency)

## Boundaries
**MUST:**
- Use fixtures for all setup (no hardcoded credentials)
- Clean up test data after each test with transaction rollback or data-only cleanup.
- Use type hints in all test code
- Run `make lint` before committing
- Keep tests under 50 lines (split into helpers if longer)

**SHALL NOT:**
- Commit .env files or secrets
- Use `print()` in tests (use logging or pytest caplog)
- Hardcode credentials or tokens
- Skip tests in CI without explicit reason
- Modify production data (tests run in isolated environment only)

## Fixtures Available
- `auth_jwt` — JWT tokens for testing (valid, expired, invalid)
- `auth_service` — auth service API client with auth
- `webserver` — web server API client
- `postgres` — PostgreSQL connection with migrations
- `rabbitmq` — RabbitMQ connection and queues
- `vault` — Vault client for secrets

## Allowed Test Types
- API tests (HTTP requests to services)
- Integration tests (multiple services together)
- Message queue tests (RabbitMQ)

## Specification-First Rule

Before adding or changing a test scenario, fixture, API client, test environment dependency, response contract, or test cleanup rule, the agent SHALL:

1. Check whether the behavior is described in `spec.md`.
2. If it is not described, propose adding it to `spec.md` before implementing the test.
3. Keep test specifications, project constitution, and test code consistent.
4. Not invent endpoint paths, authentication flows, status codes, token TTLs, or response fields without specification support.

## Жизненный цикл тестового окружения auth-service

Контракт окружения и загрузки данных описан в `specs/autotests/pipeline.md`.
Для полного изолированного цикла используйте integration-run, для подготовки — integration-up.
Локально один стенд на постоянных портах; seed/test/logs/down не требуют RUN_ID.
CI сохраняет явный RUN_ID и отдельные ресурсы.
SQL остаются в testdata/auth-service; tools/seed_auth.py вызывает общий загрузчик
фикстуры без pytest. Все SQL выполняются атомарно, без migrate и таблицы версий.
Для IDE PYTEST_CONFIG выбирает YAML из pytests; default config.yaml потребителя. Локальный запуск собирает текущие тесты и SQL.
Make-команда авторизации отключает автоматические отчёты Allure; остальные наборы сохраняют настройки.
Локальная ошибка сохраняет окружение и текстовые логи; контейнерный успех удаляет их.
В AUTH_MODE=host зависимостями управляет containers-up/down из auth-service.
Повторный host-run не перезапускает инфраструктуру; SEED_DATA=false пропускает seed локально.
CI всегда собирает логи перед попыткой уборки. Ручные тесты требуют ручного down.
Одноразовые тестовые реквизиты testkit допустимы; настоящие секреты по-прежнему запрещены.
Не меняйте отдельный workflow webserver.

Для host/host не требовать integration-up и не вызывать Docker: seed и pytest запускаются
на хосте с одним PYTEST_CONFIG (по умолчанию config.yaml pytests). Локальные YAML
пользователя не переписывать и не коммитить. Данные подготавливает pytest либо отдельная Make-команда.
Compose overlays нужны только контейнерным/смешанным сценариям.


## Подготовка данных фикстурой (актуальный контракт)

Для auth-service сессионная autouse-фикстура выполняет все testdata/auth-service/*.up.sql
через psycopg одной транзакцией. ON CONFLICT по фиксированным тестовым ключам позволяет
повторный запуск; другие записи не затрагиваются. Базовый набор остаётся для IDE,
временные ресурсы отдельных тестов очищаются их фикстурами. SEED_DATA=false локально
пропускает подготовку; CI требует true. Прямая make test-data-auth-service-up использует
тот же загрузчик без запуска pytest. CLI migrate и история версий тестовых данных
не используются. Миграции схемы выполняет только auth-service.
