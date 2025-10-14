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
