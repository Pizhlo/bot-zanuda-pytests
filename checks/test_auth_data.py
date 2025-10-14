"""Проверки подготовки SQL без сервиса, Docker и пользовательского config.yaml."""

import io
from inspect import unwrap
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, patch

import psycopg

from tests.fixtures import auth_data
from tools import seed_auth


class AuthDataPreparationTest(unittest.TestCase):
    """Проверяет единый загрузчик, атомарность вызовов и безопасные ошибки."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        settings = {"TESTDATA_PATH": str(self.root)}
        self.env = patch.dict(os.environ, settings, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        (self.root / "002_second.up.sql").write_text("SELECT 2;")
        (self.root / "001_first.up.sql").write_text("SELECT 1;")
        (self.root / "001_first.down.sql").write_text("DO NOT RUN")

    def test_files_run_in_order_in_one_transaction(self) -> None:
        connection = MagicMock()
        with patch.object(auth_data, "connect_database", return_value=connection):
            self.assertEqual(auth_data.prepare_auth_data(), 2)
        self.assertEqual(connection.__enter__.call_count, 1)
        queries = connection.__enter__.return_value.execute.call_args_list
        statements = [call.args[0] for call in queries]
        self.assertEqual(statements[-2:], ["SELECT 1;", "SELECT 2;"])
        connection.__exit__.assert_called_once_with(None, None, None)

    def test_sql_failure_rolls_back_safely(self) -> None:
        connection = MagicMock()
        connection.__enter__.return_value.execute.side_effect = [
            None, None, None, psycopg.ProgrammingError("password=hidden-value"),
        ]
        with patch.object(auth_data, "connect_database", return_value=connection):
            with self.assertRaisesRegex(auth_data.AuthDataError, "002_second.up.sql") as caught:
                auth_data.prepare_auth_data()
        self.assertNotIn("hidden-value", str(caught.exception))
        self.assertIs(connection.__exit__.call_args.args[0], psycopg.ProgrammingError)

    def test_empty_directory_fails_before_connection(self) -> None:
        with patch.dict(os.environ, {"TESTDATA_PATH": str(self.root / "missing")}):
            with patch.object(auth_data, "connect_database") as connect:
                with self.assertRaisesRegex(auth_data.AuthDataError, "Missing or empty"):
                    auth_data.prepare_auth_data()
                connect.assert_not_called()

    def test_yaml_connection_and_explicit_url(self) -> None:
        config = self.root / "custom.yaml"
        config.write_text(
            "postgres: {host: localhost, port: 5432, dbname: test, user: test, password: test}"
        )
        with patch.dict(os.environ, {"PYTEST_CONFIG": str(config)}):
            with patch.object(auth_data.psycopg, "connect") as connect:
                auth_data.connect_database()
                self.assertEqual(connect.call_args.kwargs["dbname"], "test")
                with patch.dict(os.environ, {"TESTDATA_DATABASE_URL": "postgres://localhost/other"}):
                    auth_data.connect_database()
                    self.assertEqual(connect.call_args.args, ("postgres://localhost/other",))

    def test_broken_yaml_is_redacted(self) -> None:
        config = self.root / "broken.yaml"
        config.write_text("password: [hidden-value")
        with patch.dict(os.environ, {"PYTEST_CONFIG": str(config)}):
            with self.assertRaises(auth_data.AuthDataError) as caught:
                auth_data.prepare_auth_data()
        self.assertNotIn("hidden-value", str(caught.exception))
        self.assertIn("database connection", str(caught.exception))


class AuthDataEntryPointTest(unittest.TestCase):
    """Fixture и CLI вызывают один загрузчик; флаги не обходят правила CI."""

    def setUp(self) -> None:
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_fixture_prepare_and_skip(self) -> None:
        with patch.object(auth_data, "prepare_auth_data") as prepare:
            unwrap(auth_data.auth_test_data)()
            prepare.assert_called_once_with()
            prepare.reset_mock()
            with patch.dict(os.environ, {"SEED_DATA": "false"}):
                unwrap(auth_data.auth_test_data)()
            prepare.assert_not_called()

    def test_invalid_setting_and_ci_skip_are_rejected(self) -> None:
        for env in ({"SEED_DATA": "typo"}, {"SEED_DATA": "false", "CI": "true"}):
            with self.subTest(env=env), patch.dict(os.environ, env):
                with self.assertRaises(auth_data.AuthDataError):
                    unwrap(auth_data.auth_test_data)()

    def test_cli_uses_same_loader_and_returns_status(self) -> None:
        with patch.object(seed_auth, "prepare_auth_data", return_value=4) as prepare:
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(seed_auth.main(), 0)
            prepare.assert_called_once_with()
            self.assertIn("4 SQL files", output.getvalue())
        with patch.object(seed_auth, "prepare_auth_data", side_effect=auth_data.AuthDataError("bad SQL")):
            with redirect_stderr(io.StringIO()) as output:
                self.assertEqual(seed_auth.main(), 1)
            self.assertIn("bad SQL", output.getvalue())
