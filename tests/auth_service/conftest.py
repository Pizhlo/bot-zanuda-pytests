"""Подготовка SQL только для набора auth-service, включая отдельный тест из IDE."""

from tests.fixtures.auth_data import auth_test_data  # noqa: F401
from tests.fixtures.empty_scope_client import (
    empty_scope_credentials as empty_scope_credentials,
)
from tests.fixtures.decision_identity import scoped_token as scoped_token
from tests.fixtures.owner_request import owner_request as owner_request
