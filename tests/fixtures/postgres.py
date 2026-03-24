from pathlib import Path
from collections.abc import Generator
import pytest

from src.config import config
from src.storages.postgres_client import PostgresClient

# Один файл — проще синхронизировать с init БД, чем строка в Python.
# Откат «чужой» транзакцией невозможен: см. docstring pg_prepare_client.
_PG_PREPARE_RESET_SQL = Path(__file__).resolve().parent / "sql" / "reset_auth_prepare.sql"


class SqlExecuter:
    """
    Класс для выполнения подготовки и сброса данных в БД.
    """
    def __init__(self, 
    up_sql: str | None= None, 
    down_sql: str | None = None,
    client: PostgresClient | None = None) -> None:
        if down_sql is None:
            raise ValueError("down_sql is required")
        
        if up_sql is None:
            raise ValueError("up_sql is required")
        
        self.up_sql = up_sql
        self.down_sql = down_sql
        self.client = client

    def upgrade(self) -> None:
        if not self.up_sql:
            return

        if self.client is None:
            raise ValueError("Client is not set")

        self.client.execute(self.up_sql)
            

    def downgrade(self) -> None:
        if not self.down_sql:
            return

        if self.client is None:
            raise ValueError("Client is not set")

        self.client.execute(self.down_sql)



@pytest.fixture()
def postgres_client() -> Generator[PostgresClient, None, None]:
    client = PostgresClient.connect(config.postgres, autocommit=True)

    try:
        yield client
    finally:
        client.close()
