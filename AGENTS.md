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
make test             # build current tests, run both isolated service environments, clean up
make test-auth-service # run only auth service tests
make test-webserver   # run only webserver tests
make integration-run # run one selected service through testkit
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
- Clean up each test's temporary data and isolated test messaging state with transaction rollback or targeted cleanup. Preserve the shared auth-service SQL baseline for repeated runs and IDE debugging; do not remove unrelated data.
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

## Auth-service test environment lifecycle

The environment and data-loading contract is documented in `specs/autotests/pipeline.md`.
Use `integration-run` for the full isolated lifecycle and `integration-up` for preparation.
Locally, use one environment with fixed ports; seed/test/logs/down do not require `RUN_ID`.
CI retains an explicit `RUN_ID` and separate resources.
SQL stays in `testdata/auth-service`; `tools/seed_auth.py` invokes the fixture's shared
loader without pytest. All SQL runs atomically, without migrate or a version table.
For IDE debugging, `PYTEST_CONFIG` selects a YAML file from pytests; the default is the
consumer's `config.yaml`. Local runs build the current tests and SQL.
The auth-service Make target disables automatic Allure reports; other suites retain
their settings. Local failures preserve the environment and text logs; successful
container runs remove them. In `AUTH_MODE=host`, auth-service's `containers-up/down`
commands manage dependencies. Repeated host runs do not restart infrastructure;
`SEED_DATA=false` skips seeding locally. CI always collects logs before attempting
cleanup. Manual test runs require an explicit down command.
Disposable test credentials from testkit are allowed; real secrets remain prohibited.
The webserver workflow is maintained separately under the BZ-206 contract in specs/autotests/pipeline.md. Preserve the auth-service workflow when changing it.

For host/host test execution, do not require `integration-up` or invoke Docker: seed and pytest run
on the host with the same `PYTEST_CONFIG` (default: pytests' `config.yaml`). Do not
rewrite or commit the user's local YAML files. Diagnostic logs/down may access jobs
owned by earlier container tests in the same session. Data is prepared by pytest or a
standalone Make command. Compose overlays are only needed for container or mixed modes.


## Fixture-based data preparation (current contract)

For auth-service, a session-scoped autouse fixture executes all
`testdata/auth-service/*.up.sql` files through psycopg in a single transaction.
`ON CONFLICT` on fixed test keys allows repeated runs without affecting other rows.
The baseline data remains available for IDE debugging; individual test fixtures clean
up their temporary resources. `SEED_DATA=false` skips preparation locally; CI requires
`true`. The standalone `make test-data-auth-service-up` command uses the same loader
without running pytest. The migrate CLI and test-data version history are not used.
Only auth-service runs schema migrations.

Webserver baseline data also remains available for repeated IDE runs. Its schema is prepared by testkit from pinned docker migrations, not by the fixture.

# Инструкции для ИИ: репозиторий интеграционных тестов

## Назначение

Pytests проверяет публичные контракты, бизнес-сценарии, межсервисное взаимодействие и наблюдаемое поведение при отказах на штатных образах. Тесты CLI, миграций, внутренних политик, формата хранения и точных вызовов адаптеров принадлежат сервису. Testkit управляет окружением. Тесты должны проверять реальные контракты, сохранять диагностическую ценность и не затрагивать production.

## Обязательное чтение

Перед изменением Python-кода и тестов ознакомься с:

- `docs/python-engineering-guide.md` — архитектура, типизация, docstring, ошибки;
- `docs/integration-testing-guidelines.md` — устройство интеграционных тестов, фикстуры, изоляция, ожидания, диагностика;
- `docs/architecture-examples.md` — удачные и неудачные решения, не копируй примеры механически;
- `docs/git-workflow.md` — правила веток, коммитов и проверок.

Если существующие соглашения репозитория отличаются, не меняй их самовольно: сначала проверь назначение и обсуди существенные расхождения.

## До начала работы — Git

1. Проверь `git status --short --branch`, текущую ветку и незакоммиченные изменения.
2. Уточни у пользователя, подходит ли текущая ветка для задачи: она может остаться от предыдущей работы. **До подтверждения не изменяй код.**
3. Работай в feature-ветке с идентификатором задачи `BZ-<номер>` (например, `BZ-123`, возможен описательный суффикс).
4. Новую feature-ветку создавай от актуального `main` только после безопасного обновления и проверки рабочего дерева. Не переноси, не сбрасывай и не прячь чужие изменения без согласования.
5. Если ID задачи неизвестен, уточни его до создания ветки/коммита. Не придумывай номер.

## Принципы реализации

- Прежде чем писать код, изучи существующие тесты, фикстуры, клиенты, фабрики данных, Makefile и CI.
- Соблюдай строгую типизацию там, где она практична; не используй `Any` как способ обхода ошибок типов.
- Выбирай функции, классы, `dataclass`, `Protocol` и паттерны осмысленно. Не создавай интерфейсы или базовые классы ради формы.
- Разделяй сценарии тестов, доступ к сервисам, подготовку/очистку данных и конфигурацию окружений.
- Предпочитай реальные интеграции внутри **изолированного test environment**; подменяй только границы, выходящие за рамки проверяемого контракта (production, внешние платные или недоступные API).
- Не скрывай сбои в `sleep`, широких `except`, автоматических повторах тестов, `pytest.skip`/`xfail` и ослабленных assertions.
- **Не переусложняй решение:** выбирай минимально достаточную реализацию. Не добавляй лишние классы, Protocol, фабрики, дополнительные уровни абстракции или настройки на гипотетическое будущее. Простые `if/else` допустимы, если они понятнее паттерна.
- **Строго соблюдай границы задачи:** если обнаружена проблема в коде, не относящемся к запросу, сообщи о ней с указанием файла, риска и предлагаемого исправления и **до любых изменений спроси согласие пользователя**. Не включай такие исправления в текущий коммит без согласования.
- Не исправляй посторонние ошибки линтеров/тестов, не переименовывай несвязанные сущности и не выполняй попутный рефакторинг без разрешения. Если проблема вне задачи блокирует работу, остановись на безопасном этапе и запроси решение.
- Все изменения должны быть ограничены задачей. Не удаляй тесты или файлы, не изменяй чужие черновики/закомментированные наработки без разрешения.
- Пиши содержательные docstring на русском, объясняющие контракты, а не пересказывающие строку кода.

## Безопасность тестового окружения

- До запуска изучи фикстуры и команды на наличие реальных сетевых вызовов, миграций, удаления данных, обращений к prod и изменения общих ресурсов.
- Используй только явно разрешённые тестовые адреса/учётные данные. Никогда не подставляй production по умолчанию.
- Не логируй секреты, токены, полные DSN и чувствительные payload.
- Не выполняй разрушительные команды на shared/prod окружении без явного согласования.
- Тесты должны очищать созданные ресурсы, но не удалять чужие данные.

## Управление ресурсами
При создании внешних ресурсов в интеграционных тестах обеспечивай их очистку даже при ошибках assertions, сетевых сбоях и частичном выполнении операции. Регистрируй очистку до проверок, способных прервать тест. Подробные требования — в docs/integration-testing-guidelines.md.

## Проверки перед каждым коммитом

1. Изучи Makefile и конфигурацию CI. Используй **существующие** команды `make lint` и `make test`, **если они определены в данном репозитории и безопасны**. Не предполагай их наличие или состав автоматически.
2. Если подходящих Make-targets нет, используй принятые проектом команды для Ruff/форматирования, проверки типов и релевантных pytest-тестов; не создавай дублирующие инструменты без необходимости.
3. Исправь обнаруженные ошибки и повтори проверки. Не отключай линтеры и не изменяй ожидаемые результаты ради зелёного статуса.
4. Если полные интеграционные тесты требуют недоступной/опасной инфраструктуры, выполни безопасные локальные проверки и явно перечисли непройденные/неисполненные проверки. Не называй работу полностью проверенной.
5. Перед **каждым** коммитом проверь состав staging area и отсутствие секретов.
6. Формат коммита: `BZ-123: добавлены тесты восстановления` — идентификатор задачи, двоеточие, описание **по-русски в прошедшем времени**. Не используй инфинитив (`добавить`) или повелительную форму.
7. Не создавай коммиты с заведомо падающими обязательными проверками. Если проверки невозможно выполнить — сообщи об ограничении, не заявляй об успешном прохождении.

Перед каждым коммитом ИИ обязан убедиться, что make lint и make test выполнены для версии кода, которая фактически попадёт в коммит. Проверка только рабочего дерева недостаточна при наличии отличий от Git index.


### Проверка содержимого коммита

Перед каждым коммитом убедись, что `make lint` и `make test`
выполнены для версии кода, которая фактически попадёт в коммит.

Проверка только рабочего дерева недостаточна, если его
содержимое отличается от Git index.

При частичном staging проверяй подготовленную версию
кода изолированно.

Не создавай коммит, пока подготовленные изменения
не прошли обязательные проверки.

Подробные требования описаны в `docs/git-workflow.md`.

## Отчёт о работе

В итоговом ответе перечисли изменения по файлам и дай ссылки на них. Для каждого тестового файла назови добавленные и обновлённые сценарии, входные условия и ожидаемые результаты. Для больших матриц сгруппируй варианты по ролям, действиям и состояниям ресурса, укажи исключения. Для файлов параметров, фикстур и общих проверок объясни их роль в этих сценариях.

Укажи, какие проверки запускались, их фактический результат и оставшиеся ограничения. Не утверждай, что инструмент запускался, если этого не было.
