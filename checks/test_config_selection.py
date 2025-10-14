"""Регрессии выбора БД: временные YAML, без настоящих реквизитов и PostgreSQL."""

from contextlib import chdir
from importlib import import_module
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from src.database_config import DatabaseConfig
from tests.fixtures import auth_data


CONFIG_NAME = "config.yaml"
DATABASE_NAME = "dbname"
CONNECT_TARGET = "tests.fixtures.auth_data.psycopg.connect"


def write_config(path: Path, postgres: dict[str, object]) -> None:
    """Пишет вымышленные настройки и создаёт их каталог, не читая настоящие YAML."""
    path.parent.mkdir(exist_ok=True)
    path.write_text(yaml.safe_dump({
        "auth_service": {"secret_key": "test-only"}, "postgres": postgres,
    }))


def assert_config_rejected(testcase: unittest.TestCase, path: Path) -> None:
    """Проверяет безопасный отказ seed и отсутствие вызова подключения к PostgreSQL."""
    settings = {"PYTEST_CONFIG": str(path)}
    with patch.dict(os.environ, settings), patch(CONNECT_TARGET) as connect:
        with testcase.assertRaises(auth_data.AuthDataError) as caught:
            auth_data.prepare_auth_data()
        testcase.assertNotIn("hidden-value", str(caught.exception))
        connect.assert_not_called()


class ConfigSelectionTest(unittest.TestCase):
    """Сопоставляет параметры реального Config и seed при разных способах запуска."""

    def setUp(self) -> None:
        """Создаёт отдельные cwd и корень SQL, чтобы обнаружить выбор неверной БД.

        Даже старая реализация прочитает только временный конфиг: ROOT загрузчика
        подменён. Окружение очищается, чтобы USER/HOST не влияли на defaults модели.
        """
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(chdir(self.root))
        repository = self.root / "repository"
        self.enterContext(patch.object(auth_data, "ROOT", repository))
        write_config(repository / CONFIG_NAME, {DATABASE_NAME: "repository_db"})
        sql = self.root / "sql"
        sql.mkdir()
        (sql / "001.up.sql").write_text("SELECT 1;")
        os.environ["TESTDATA_PATH"] = str(sql)
        write_config(self.root / CONFIG_NAME, {DATABASE_NAME: "cwd_db"})

    def assert_shared_connection(self, expected_db: str) -> None:
        """Проверяет параметры клиента тестов против аргументов psycopg у seed.

        Config импортируется после подготовки временного cwd: его глобальный
        экземпляр также не читает пользовательские настройки и не подключается к БД.
        """
        config_type = import_module("src.config").Config
        postgres = config_type().postgres
        self.assertEqual(postgres.dbname, expected_db)
        with patch(CONNECT_TARGET) as connect:
            auth_data.connect_database()
            connect.assert_called_once_with(**postgres.model_dump(), connect_timeout=10)

    def test_config_paths_agree(self) -> None:
        """Проверяет cwd, пустой override и относительный/абсолютный PYTEST_CONFIG."""
        alternate = self.root / "alternate.yaml"
        write_config(alternate, {DATABASE_NAME: "explicit_db"})
        for override in (None, "", alternate.name, str(alternate)):
            with self.subTest(override=override):
                settings = {} if override is None else {"PYTEST_CONFIG": override}
                with patch.dict(os.environ, settings):
                    self.assert_shared_connection("explicit_db" if override else "cwd_db")

    def test_postgres_defaults_agree(self) -> None:
        """Оба потребителя дополняют необязательные поля, включая всю секцию postgres."""
        for postgres in ({DATABASE_NAME: "partial_db"}, {}, None):
            with self.subTest(postgres=postgres):
                payload = {"auth_service": {"secret_key": "test-only"}}
                if postgres is not None:
                    payload["postgres"] = postgres
                (self.root / CONFIG_NAME).write_text(yaml.safe_dump(payload))
                self.assert_shared_connection("partial_db" if postgres else "postgres")

    def test_standalone_seed_needs_no_auth_service(self) -> None:
        """Seed использует только PostgreSQL, не создавая полный Config с auth_service."""
        (self.root / CONFIG_NAME).write_text("postgres: {dbname: seed_only}\n")
        expected = DatabaseConfig().postgres
        with patch(CONNECT_TARGET) as connect:
            auth_data.connect_database()
            connect.assert_called_once_with(**expected.model_dump(), connect_timeout=10)

    def test_invalid_config_is_safe(self) -> None:
        """Опечатка пути и ошибки YAML/типов не дают seed подключиться по defaults."""
        invalid = self.root / "invalid.yaml"
        cases = [
            (self.root / "missing.yaml", None), (self.root, None),
            (invalid, "postgres: [hidden-value"),
            (invalid, "postgres: {port: hidden-value}"),
            (invalid, "postgres: hidden-value"),
            (invalid, "- hidden-value"),
        ]
        for path, yaml_text in cases:
            with self.subTest(path=path, yaml_text=yaml_text):
                if yaml_text is not None:
                    path.write_text(yaml_text)
                assert_config_rejected(self, path)

    def test_explicit_dsn_bypasses_yaml(self) -> None:
        """Явный DSN остаётся независимым от YAML, включая отсутствующий файл."""
        settings = {
            "PYTEST_CONFIG": str(self.root / "missing.yaml"),
            "TESTDATA_DATABASE_URL": "postgresql://localhost/explicit_seed",
        }
        with patch.dict(os.environ, settings):
            with patch(CONNECT_TARGET) as connect:
                auth_data.connect_database()
                connect.assert_called_once_with(settings["TESTDATA_DATABASE_URL"], connect_timeout=10)
