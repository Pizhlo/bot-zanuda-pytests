"""Базовые данные webserver: тот же атомарный механизм, отдельная legacy-схема."""

import logging
import os
from pathlib import Path

import pytest

from tests.fixtures.auth_data import AuthDataError, ROOT, prepare_sql_data

logger = logging.getLogger(__name__)


def prepare_webserver_data() -> int:
    """Готовит только webserver SQL; не выполняет миграции и не очищает чужие строки."""
    directory = Path(os.environ.get("TESTDATA_PATH") or ROOT / "testdata/webserver")
    sources = sorted(path for path in directory.glob("*.up.sql") if path.is_file())
    if not sources:
        raise AuthDataError(f"Missing or empty webserver test data directory: {directory}")
    return prepare_sql_data(sources)


@pytest.fixture(scope="session", autouse=True)
def webserver_test_data() -> None:
    """Подготавливает baseline для прямого pytest и сохраняет его для IDE."""
    setting = os.environ.get("SEED_DATA") or "true"
    if setting not in ("true", "false"):
        raise AuthDataError("SEED_DATA must be true or false")
    if setting == "false":
        if os.environ.get("CI", "").lower() in ("true", "1"):
            raise AuthDataError("CI requires SEED_DATA=true")
        logger.info("Webserver data preparation skipped: SEED_DATA=false")
        return
    prepare_webserver_data()
