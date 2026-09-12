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
- Tests run in isolated Docker environment
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