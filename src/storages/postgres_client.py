from collections.abc import Mapping, Sequence
from typing import Any, Self

from psycopg import Connection, connect
from psycopg.rows import dict_row

from src.config import PostgresConfig


class PostgresClient:
    """Клиент для прямых запросов к PostgreSQL (тесты, миграции данных)."""

    def __init__(self, connection: Connection[Any]) -> None:
        self._conn = connection

    @classmethod
    def connect(cls, pg_config: PostgresConfig, *, autocommit: bool = False) -> Self:
        conn = connect(
            host=pg_config.host,
            port=pg_config.port,
            dbname=pg_config.dbname,
            user=pg_config.user,
            password=pg_config.password,
            autocommit=autocommit,
        )
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    @property
    def raw_connection(self) -> Connection[Any]:
        return self._conn

    def execute(
        self,
        query: str,
        query_params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> None:
        self._conn.execute(query, query_params)

    def fetch_all(
        self,
        query: str,
        query_params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, query_params)
            return list(cur.fetchall())

    def fetch_one(
        self,
        query: str,
        query_params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        rows = self.fetch_all(query, query_params)
        return rows[0] if rows else None
