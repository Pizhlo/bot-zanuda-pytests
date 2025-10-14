"""Общая подготовка PostgreSQL для фикстуры auth-service и отдельной Make-команды.

SQL остаются рядом с тестами. Здесь только подключение, порядок и транзакция:
схему создаёт приложение, повторяемость обеспечивают ON CONFLICT в самих SQL.
Базовые записи сохраняются для IDE; этот модуль не удаляет БД и чужие данные.
"""

import logging
import os
from pathlib import Path
from typing import Any

import psycopg
import pytest
import yaml

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


class AuthDataError(RuntimeError):
    """Безопасная диагностика подготовки без URL, паролей и содержимого YAML."""


def sql_sources() -> list[Path]:
    """Находит up-файлы в порядке зависимостей независимо от текущего каталога.

    TESTDATA_PATH нужен для явного выбора набора. Down-файлы не запускаются:
    подготовка обновляет свой базовый набор, а не сбрасывает всю тестовую БД.
    Проверка выполняется до подключения, чтобы опечатка пути не меняла данные.
    """
    directory = Path(os.environ.get("TESTDATA_PATH") or ROOT / "testdata/auth-service")
    sources = sorted(path for path in directory.glob("*.up.sql") if path.is_file())
    if not sources:
        raise AuthDataError(f"Missing or empty auth test data directory: {directory}")
    return sources


def connect_database() -> psycopg.Connection[Any]:
    """Подключается по тому же YAML, который использует pytest, либо по явному DSN.

    Для команды подготовки достаточно раздела postgres: остальные клиенты тестов
    не создаются. Настоящие реквизиты используются только для подключения.
    TESTDATA_DATABASE_URL оставлен для явной работы с отдельной тестовой БД.
    """
    database_url = os.environ.get("TESTDATA_DATABASE_URL")
    if database_url:
        return psycopg.connect(database_url, connect_timeout=10)
    path = Path(os.environ.get("PYTEST_CONFIG") or ROOT / "config.yaml")
    postgres = yaml.safe_load(path.read_text())["postgres"]
    return psycopg.connect(
        host=postgres["host"], port=postgres["port"], dbname=postgres["dbname"],
        user=postgres["user"], password=postgres["password"], connect_timeout=10,
    )


def prepare_auth_data() -> int:
    """Атомарно приводит фиксированные тестовые записи к значениям из SQL.

    Одна транзакция объединяет все файлы: если последний SQL ошибочен, изменения
    предыдущих тоже откатываются. Commit нужен до HTTP-запросов: сервис работает
    через своё соединение и не видит незакоммиченные изменения фикстуры.
    Ограничения ожидания блокировок/SQL не дают подготовке зависнуть бессрочно.
    История migrate не читается и не меняется, поэтому старые версии/dirty не мешают.
    """
    sources = sql_sources()
    stage = "database connection"
    try:
        with connect_database() as connection:
            connection.execute("SET LOCAL lock_timeout = '10s'")
            connection.execute("SET LOCAL statement_timeout = '60s'")
            for source in sources:
                stage = source.name
                connection.execute(source.read_text())
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError, psycopg.Error) as error:  # noqa: WPS239
        # Исключения подключения/YAML могут содержать пароль; сохраняем лишь тип и этап.
        raise AuthDataError(
            f"Auth data preparation failed at {stage} ({type(error).__name__})"
        ) from None
    logger.info("Auth test data prepared: %s SQL files", len(sources))
    return len(sources)


@pytest.fixture(scope="session", autouse=True)
def auth_test_data() -> None:
    """Готовит базовый набор один раз перед auth-service тестами, включая запуск из IDE.

    Фикстура импортируется только в tests/auth_service/conftest.py и не влияет на
    webserver. SEED_DATA=false позволяет исследовать уже подготовленные данные.
    Базовый набор остаётся после pytest для отладки, как после отдельного seed;
    очисткой ресурсов конкретных сценариев управляют их собственные фикстуры.
    """
    setting = os.environ.get("SEED_DATA") or "true"
    if setting not in ("true", "false"):
        raise AuthDataError("SEED_DATA must be true or false")
    if setting == "false":
        if os.environ.get("CI", "").lower() in ("true", "1"):
            raise AuthDataError("CI requires SEED_DATA=true")
        logger.info("Auth data preparation skipped: SEED_DATA=false")
        return
    prepare_auth_data()
