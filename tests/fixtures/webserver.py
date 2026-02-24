import pytest

from src.api_clients.webserver import WebServerAPIClient, WebServerV0APIClient


@pytest.fixture(scope="session")
def webserver_v0_api_client() -> WebServerV0APIClient:
    return WebServerV0APIClient()


@pytest.fixture(scope="session")
def webserver_api_client() -> WebServerAPIClient:
    return WebServerAPIClient()



