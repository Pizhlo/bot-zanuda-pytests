"""Общая логика для тестов login (миграции БД, предупреждения) — снижает сложность тестового модуля."""

from collections.abc import Generator
from contextlib import contextmanager
import logging

from src.storages.postgres_client import PostgresClient
from tests.fixtures.postgres import SqlExecuter

logger = logging.getLogger(__name__)


@contextmanager
def postgres_sql_migration(
    postgres_client: PostgresClient,
    up_sql: str | None,
    down_sql: str | None,
) -> Generator[None, None, None]:
    """Выполняет up_sql перед телом и down_sql в finally (оба заданы или оба None)."""
    if up_sql is not None and down_sql is None:
        raise ValueError("down_sql is required when up_sql is set")
    if up_sql is None and down_sql is not None:
        raise ValueError("up_sql is required when down_sql is set")

    executer: SqlExecuter | None = None
    if up_sql is not None and down_sql is not None:
        executer = SqlExecuter(up_sql=up_sql, down_sql=down_sql, client=postgres_client)
        executer.upgrade()

    try:
        yield
    finally:
        if executer is not None:
            executer.downgrade()