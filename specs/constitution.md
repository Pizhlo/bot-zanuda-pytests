# Project Constitution

## Immutable Constraints
The system SHALL use Python 3.13+ for all test code.
The system SHALL use pytest as the test framework.
The system SHALL use uv as package manager.
The system SHALL require minimum 80% test coverage for new code.
The system MUST NOT commit .env files or secrets to version control.

## Technology Boundaries
The system SHALL use PostgreSQL for test database fixtures.
The system SHALL use RabbitMQ for message queue testing.
The system MAY use Redis for caching tests (optional).
The system SHALL use Docker Compose for test environment setup.
The system SHALL use mypy for type checking.
The system SHALL use flake8 and ruff for linting.

## Test Quality
All tests SHALL be independent and idempotent (can run in any order).
All tests SHALL clean up their own temporary data and isolated test messaging state after each test.
The shared auth-service SQL baseline SHALL remain available for repeated runs and IDE debugging; per-test cleanup SHALL NOT remove it or unrelated data.
All fixtures SHALL be in `tests/fixtures/` directory.
All API clients SHALL be in `src/api_clients/` directory.

## CI/CD Requirements
All commits SHALL pass `make lint` validation.
All commits SHALL pass `make typecheck` (mypy).
Changes to auth-service tests and their shared dependencies on branches within this repository SHALL pass the corresponding CI checks.
The job that requires secrets SHALL be skipped for fork PRs before checking out the private testkit; a skipped job does not mean the tests passed.
The auth-service workflow SHALL use the path filters documented in `specs/autotests/pipeline.md`; manual runs remain available.
Test coverage SHALL be reported in CI.

## Fixture-based data preparation (current contract)

For auth-service, a session-scoped autouse fixture executes all
`testdata/auth-service/*.up.sql` files through psycopg in a single transaction.
`ON CONFLICT` on fixed test keys allows repeated runs without affecting other rows.
The baseline data remains available for IDE debugging; individual test fixtures clean
up their temporary resources. `SEED_DATA=false` skips preparation locally; CI requires
`true`. The standalone `make test-data-auth-service-up` command uses the same loader
without running pytest. The migrate CLI and test-data version history are not used.
Only auth-service runs schema migrations.


## Webserver integration environment (BZ-206)

The webserver profile SHALL be selected explicitly with INTEGRATION_SERVICE=webserver.
The default profile and all existing auth-service commands, state and image inputs
SHALL remain compatible. WEBSERVER_MODE and TEST_MODE SHALL support all four
host/container combinations on Linux; CI SHALL use container/container.

The webserver environment SHALL prepare PostgreSQL, Redis and RabbitMQ. It SHALL
apply the explicit schema manifest from the pinned docker source before service
readiness, seed and tests. Migration 000014 (Sequin deployment configuration) SHALL
NOT run. Repeated preparation SHALL preserve data and reject a changed migration
manifest on an existing environment. Auth-service continues to own its migrations.
Webserver tests SHALL NOT require auth-service, db-worker or Elasticsearch processes.

The stable integration-up/seed/rabbitmq-setup/test/logs/down/run interface SHALL
support webserver. Up SHALL stop before seed/tests. Webserver containers-up/down
SHALL manage IDE dependencies and schema preparation; the runner SHALL NOT manage
the IDE process or its dependencies. Host/host seed and tests SHALL not invoke
Docker or require up. Container jobs retained from earlier runs remain accessible
through logs/down. User YAML files SHALL NOT be rewritten.

Webserver SQL SHALL come from the same pytests version as the tests and load through
one atomic, repeatable session fixture or standalone seed. The shared baseline SHALL
remain for IDE use; unrelated data SHALL remain intact. SEED_DATA=false SHALL be
local-only. Notes tests SHALL purge only their test queue before each request, wait
for messages with a bounded timeout, validate request identity and clean up their
own messaging state. The full health/metrics/notes suite SHALL run.

Service CI SHALL test its current commit image with published tests (latest or an
explicit tag). Pytests CI and local execution SHALL use current tests/data against
published webserver latest or WEBSERVER_IMAGE. CI SHALL skip secret-dependent fork
PR jobs before private checkout, isolate runs without host ports, show actual image
IDs/digests and pytest results, then attempt cleanup even after preparation or log
errors. Local container success SHALL clean up its resources; failures SHALL retain
them and diagnostics. Host runs SHALL retain IDE infrastructure. Cleanup SHALL
never adopt or remove another project's resources.


## Общий запуск всех сервисов

`make test` собирает текущий checkout pytests один раз и последовательно запускает
наборы auth-service и webserver в двух отдельных контейнерных стендах testkit.
Каждому стенду назначается уникальный RUN_ID; порты хоста не публикуются.
Используются встроенные конфиги и SQL образа, SEED_DATA=true. Локальные режимы,
PYTEST_CONFIG, TESTDATA_PATH/TESTDATA_DATABASE_URL и пользовательский RUN_ID
не переопределяют этот изолированный запуск. AUTH_IMAGE/WEBSERVER_IMAGE позволяют
выбрать образы сервисов; по умолчанию используются опубликованные latest.
Оба набора запускаются даже при ошибке первого. Общая ошибка сборки блокирует оба.
Логи сохраняются в .logs/<общий-id>/; итог содержит статус каждого сервиса.
Любая ошибка тестов, подготовки, логирования или уборки даёт ненулевой exit code.
При любом исходе выполняется попытка удалить только ресурсы текущего запуска;
при Ctrl+C/SIGTERM выполняется уборка активного стенда, второй набор не запускается.
SIGKILL не позволяет гарантировать уборку. Команды test-auth-service/test-webserver
остаются прямым pytest по готовому окружению; integration-run сохраняет свой контракт.
