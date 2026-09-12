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
REQ-003: The system SHALL clean up test data and test messaging state after each test, with no side effects.
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
- GIVEN test A creates data in database
- WHEN test A completes
- AND test B runs
- THEN test B sees clean database (test A data is cleaned up)

### Scenario: Bot tests [PLANNED]
- GIVEN bot is running
- WHEN user sends message to bot
- THEN bot processes message correctly