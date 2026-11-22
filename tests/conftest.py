import pytest

pytest.register_assert_rewrite("assertions.webserver", "assertions.auth_service", "assertions.decisions", "assertions.record_decisions")

pytest_plugins = [
    "tests.fixtures.telegram",
    "tests.fixtures.webserver",
    "tests.fixtures.rabbitmq",
    "tests.fixtures.auth_service",
    "tests.fixtures.vault",
    "tests.fixtures.postgres",
    "tests.fixtures.openfga",
    "tests.fixtures.decision_actors",
    "tests.fixtures.decisions",
    "tests.fixtures.decision_records",
    "tests.fixtures.stored_note",
]
