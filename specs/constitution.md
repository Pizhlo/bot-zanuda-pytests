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
All tests SHALL clean up after themselves (no side effects).
All fixtures SHALL be in `tests/fixtures/` directory.
All API clients SHALL be in `src/api_clients/` directory.

## CI/CD Requirements
All commits SHALL pass `make lint` validation.
All commits SHALL pass `make typecheck` (mypy).
All pull requests SHALL have passing tests.
Test coverage SHALL be reported in CI.