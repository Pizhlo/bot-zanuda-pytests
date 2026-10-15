# Autotests Specification

## Purpose
Provide end-to-end test coverage for all project services (web server, auth service, bot).
Currently testing web server and auth service APIs.

## Architecture Overview
- Tests run in isolated Docker environment
- Each test suite has its own database schema
- Fixtures in `tests/fixtures/` (JWT, db, rabbitmq, vault)
- API clients in `src/api_clients/`

## Test Categories

### API Tests
- HTTP requests to services
- Validate status codes, response bodies, headers
- Test happy path and error cases

### Integration Tests
- Multiple services together (web server + auth service)
- Database + application
- Message queue + application

## Requirements

REQ-001: The system SHALL provide API tests for all public endpoints.
REQ-002: WHEN a new endpoint is added, tests SHALL be added in the same PR.
REQ-003: The system SHALL clean up each test's temporary data and isolated test messaging state after the test. Per-test cleanup SHALL preserve the shared auth-service SQL baseline for repeated runs and IDE debugging and SHALL NOT remove unrelated data.
REQ-004: All tests SHALL be independent (can run in any order).
REQ-005: The system SHALL use fixtures for all setup (no hardcoded credentials).
REQ-006: IF a test fails, it SHALL provide a clear error message with redacted request/response details and SHALL mask all secrets and tokens.
REQ-007: The system SHALL report test coverage in CI.

## RabbitMQ Integration Testing Requirements

Tests that verify publication of domain events to RabbitMQ SHALL validate message identity and isolate test data.

### Queue Cleanup

Before each test that consumes messages from a RabbitMQ queue, the test fixture SHALL purge the queue to ensure it is empty.

Tests SHALL NOT rely on messages from previous tests.

### Message Identity Validation

Tests that verify published events SHALL:

- Include a unique identifier in the published message payload (for example, `event_id`).
- Assert that the received message `event_id` matches the expected value.
- Compare the full message payload with the expected payload.

### Acknowledgement Policy

Tests SHALL acknowledge messages only after successful payload validation.

Tests SHALL NOT use `auto_ack=True` when validating message content.

### Requirements

REQ-RABBITMQ-TEST-001: Before each test that consumes messages from a RabbitMQ queue, the test fixture SHALL purge the queue.

REQ-RABBITMQ-TEST-002: Tests verifying event publication SHALL include a unique identifier in the published message payload.

REQ-RABBITMQ-TEST-003: Tests verifying event publication SHALL assert that the received message identifier matches the expected value.

REQ-RABBITMQ-TEST-004: Tests verifying event publication SHALL compare the full message payload with the expected payload.

REQ-RABBITMQ-TEST-005: Tests SHALL acknowledge messages only after successful payload validation.

REQ-RABBITMQ-TEST-006: Tests SHALL NOT use `auto_ack=True` when validating message content.

## Scenarios

### Scenario: Auth service health check - allowed
- GIVEN auth service is running
- WHEN GET /health is called
- THEN the system returns 200 OK

### Scenario: Auth service login - valid service client

- GIVEN an active service client exists
- AND the client secret is available through Vault
- WHEN POST `/auth/login` is called with `grant_type=client_credentials`, valid `client_id`, and valid `client_secret`
- THEN the system returns 200 OK
- AND the response contains a valid JWT service token
- AND the response contains the effective scope list
- AND `expires_in` in the response equals 3600

### Scenario: Auth service login - invalid service credentials

- GIVEN an active service client exists
- WHEN POST `/auth/login` is called with an invalid `client_secret`
- THEN the system returns 401 Unauthorized
- AND no token is issued

### Scenario: Auth service UpdateResource - create note resource

- GIVEN an authenticated service client with valid JWT token
- AND the client sends `UpdateResourceRequest` with `resource.type="note"`, `operation="create"`, and valid relations
- WHEN the `UpdateResource` API is called
- THEN the system returns 200 OK
- AND the note resource tuple is written to OpenFGA
- AND the response contains the written tuple

### Scenario: Auth service UpdateResource - create reminder resource

- GIVEN an authenticated service client with valid JWT token
- AND the client sends `UpdateResourceRequest` with `resource.type="reminder"`, `operation="create"`, and valid relations
- WHEN the `UpdateResource` API is called
- THEN the system returns 200 OK
- AND the reminder resource tuple is written to OpenFGA

### Scenario: Auth service UpdateResource - invalid operation for change_type

- GIVEN an authenticated service client
- AND the client sends `UpdateResourceRequest` with `change_type="resource_added"` and `operation="delete"`
- WHEN the `UpdateResource` API is called
- THEN the system returns 400 Bad Request
- AND no tuple is written to OpenFGA

### Scenario: Auth service UpdateResource - idempotent retry

- GIVEN an authenticated service client
- AND a previous `UpdateResourceRequest` with the same `idempotency_key` and payload was successfully processed
- WHEN the same request is sent again
- THEN the system returns 200 OK
- AND the stored response is returned
- AND no new tuple is written to OpenFGA

### Scenario: RabbitMQ message publish/consume
- GIVEN RabbitMQ is running
- AND the test queue is purged
- WHEN a message with unique `event_id` is published to the queue
- AND the message is consumed with `auto_ack=False`
- THEN the system receives the message
- AND the received `event_id` matches the published `event_id`
- AND the full message payload matches the expected payload
- AND the message is acknowledged only after successful validation

### Scenario: Test isolation - no side effects
- GIVEN the shared baseline is prepared and test A creates temporary data in the database
- WHEN test A completes
- AND test B runs
- THEN test B sees the shared baseline without test A's temporary data
- AND cleanup preserves unrelated data

### Scenario: Bot tests [PLANNED]
- GIVEN bot is running
- WHEN user sends message to bot
- THEN bot processes message correctly

### Scenario: Repeating resource creation on a retained environment

- GIVEN the service and infrastructure are still running after the previous pytest run
- WHEN the note, space, and reminder creation scenarios run
- THEN the resources created by the tests use distinct identifiers
- AND after each scenario, the fixture removes the created relationships through the test OpenFGA API (delete is not yet implemented in the auth-service API)
- AND the conflict scenario creates its own resource beforehand and does not depend on parameter order
- AND preparation does not clear other environment data or restart the service

Before validating an audit message, the fixture purges only the auth-service test error
queue so that messages from a previous failed run do not replace the new scenario's result.


## Fixture-based data preparation (current contract)

For auth-service, a session-scoped autouse fixture executes all
`testdata/auth-service/*.up.sql` files through psycopg in a single transaction.
`ON CONFLICT` on fixed test keys allows repeated runs without affecting other rows.
The baseline data remains available for IDE debugging; individual test fixtures clean
up their temporary resources. `SEED_DATA=false` skips preparation locally; CI requires
`true`. The standalone `make test-data-auth-service-up` command uses the same loader
without running pytest. The migrate CLI and test-data version history are not used.
Only auth-service runs schema migrations.


### Cleanup after resource preparation fails

- WHEN the preparatory request for the 409 scenario writes relationships and then returns an error or raises an exception
- THEN the `isolated_resource` fixture attempts to remove its unique object's relationships in `finally`, even before `yield`
- AND the preparation error is preserved, the test body does not run, and baseline records and other objects are not deleted


## Shared PostgreSQL configuration

Pytest and the auth-service data loader SHALL read PostgreSQL settings through the
same YAML source and PostgresConfig model. PYTEST_CONFIG selects the file; otherwise,
config.yaml in the process working directory is used. Relative paths are resolved
from that directory. The integration runner supplies an explicit path as before.
Missing optional PostgreSQL fields or the entire postgres section SHALL use the same
defaults. Standalone seed SHALL accept PostgreSQL-only YAML without auth_service.
A missing/non-file config path or invalid YAML SHALL fail before seed connects to
the database; diagnostics SHALL NOT disclose YAML contents or credentials.
TESTDATA_DATABASE_URL remains an explicit override for seed only.

### Scenario: Seed follows the tests' configuration
- GIVEN pytest starts outside the repository with a valid local config.yaml
- WHEN its auth-service data fixture runs without PYTEST_CONFIG
- THEN both clients and seed use that file's PostgreSQL settings
- AND partial PostgreSQL settings receive the same defaults

### Scenario: Standalone seed with an invalid config path
- GIVEN PYTEST_CONFIG names a missing file or a directory and no explicit DSN is set
- WHEN the standalone seed command runs
- THEN it reports a safe error and does not attempt a database connection
