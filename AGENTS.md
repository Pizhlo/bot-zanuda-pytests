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
