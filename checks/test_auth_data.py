"""Проверки подготовки SQL без сервиса, Docker и пользовательского config.yaml."""

import io
from inspect import unwrap
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, call, patch

import psycopg

from tests.fixtures import auth_data
from tools import seed_auth


class AuthDataTestCase(unittest.TestCase):
    """Изолированный набор SQL и переменные окружения."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        settings = {"TESTDATA_PATH": str(self.root)}  # noqa: WPS226
        self.env = patch.dict(os.environ, settings, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        (self.root / "002_second.up.sql").write_text("SELECT 2;")
        (self.root / "001_first.up.sql").write_text("SELECT 1;")
        (self.root / "001_first.down.sql").write_text("DO NOT RUN")


class AuthDataPreparationTest(AuthDataTestCase):
    """Общий загрузчик, порядок SQL и безопасные ошибки."""

    def test_files_run_in_order_in_one_transaction(self) -> None:
        connection = MagicMock()
        with patch.object(auth_data, "connect_database", return_value=connection):  # noqa: WPS226
            self.assertEqual(auth_data.prepare_auth_data(), 2)
        self.assertEqual(connection.__enter__.call_count, 1)
        queries = connection.__enter__.return_value.execute.call_args_list
        statements = [call.args[0] for call in queries]
        self.assertEqual(statements[-2:], ["SELECT 1;", "SELECT 2;"])
        connection.__exit__.assert_called_once_with(None, None, None)

    def test_sql_failure_rolls_back_safely(self) -> None:
        connection = MagicMock()
        connection.__enter__.return_value.execute.side_effect = [
            None,
            None,
            None,
            psycopg.ProgrammingError("password=hidden-value"),
        ]
        with patch.object(auth_data, "connect_database", return_value=connection):
            with self.assertRaisesRegex(
                auth_data.AuthDataError, "002_second.up.sql"
            ) as caught:
                auth_data.prepare_auth_data()
        self.assertNotIn("hidden-value", str(caught.exception))
        self.assertIs(connection.__exit__.call_args.args[0], psycopg.ProgrammingError)

    def test_empty_directory_fails_before_connection(self) -> None:
        with patch.dict(os.environ, {"TESTDATA_PATH": str(self.root / "missing")}):
            with patch.object(auth_data, "connect_database") as connect:
                with self.assertRaisesRegex(
                    auth_data.AuthDataError, "Missing or empty"
                ):
                    auth_data.prepare_auth_data()
                connect.assert_not_called()

    def test_yaml_connection_and_explicit_url(self) -> None:
        config = self.root / "custom.yaml"
        config.write_text(
            "postgres: {host: localhost, port: 5432, dbname: test, user: test, password: test}"
        )
        with patch.dict(os.environ, {"PYTEST_CONFIG": str(config)}):  # noqa: WPS226
            with patch.object(auth_data.psycopg, "connect") as connect:  # noqa: WPS226
                auth_data.connect_database()
                self.assertEqual(connect.call_args.kwargs["dbname"], "test")
                with patch.dict(
                    os.environ, {"TESTDATA_DATABASE_URL": "postgres://localhost/other"}
                ):
                    auth_data.connect_database()
                    self.assertEqual(
                        connect.call_args.args, ("postgres://localhost/other",)
                    )

    def test_broken_yaml_is_redacted(self) -> None:
        config = self.root / "broken.yaml"
        config.write_text("password: [hidden-value")
        with patch.dict(os.environ, {"PYTEST_CONFIG": str(config)}):
            with self.assertRaises(auth_data.AuthDataError) as caught:
                auth_data.prepare_auth_data()
        self.assertNotIn("hidden-value", str(caught.exception))
        self.assertIn("database connection", str(caught.exception))

    def test_repeat_preparation_reapplies_all_sql(self) -> None:
        connection = MagicMock()
        expected = [
            call("SET LOCAL lock_timeout = '10s'"),
            call("SET LOCAL statement_timeout = '60s'"),
            call("SELECT 1;"),
            call("SELECT 2;"),
        ]
        with patch.object(auth_data, "connect_database", return_value=connection):
            self.assertEqual(auth_data.prepare_auth_data(), 2)
            self.assertEqual(auth_data.prepare_auth_data(), 2)
        self.assertEqual(
            connection.__enter__.return_value.execute.call_args_list, expected * 2
        )
        self.assertEqual(
            connection.__exit__.call_args_list,
            [call(None, None, None) for _ in range(2)],
        )


class AuthDataDiscoveryTest(AuthDataTestCase):
    """Поиск выполняемых SQL до подключения к БД."""

    def test_discovery_selects_only_top_level_up_sql(self) -> None:
        (self.root / "003_directory.up.sql").mkdir()
        nested = self.root / "nested"
        nested.mkdir()
        (nested / "004_nested.up.sql").write_text("DO NOT RUN")
        (self.root / "README.md").write_text("not SQL")
        self.assertEqual(
            auth_data.sql_sources(),
            [
                self.root / "001_first.up.sql",
                self.root / "002_second.up.sql",
            ],
        )

    def test_default_data_path_ignores_cwd(self) -> None:
        default = self.root / "testdata/auth-service"
        default.mkdir(parents=True)
        source = default / "001_default.up.sql"
        source.write_text("SELECT 3;")
        for selector in (None, ""):
            with (
                self.subTest(selector=selector),
                patch.object(auth_data, "ROOT", self.root),
                patch.dict(os.environ, {}, clear=True),
            ):
                if selector is not None:
                    os.environ["TESTDATA_PATH"] = selector
                self.assertEqual(auth_data.sql_sources(), [source])

    def test_empty_directory_never_connects(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        with patch.dict(os.environ, {"TESTDATA_PATH": str(empty)}):
            with patch.object(auth_data, "connect_database") as connect:
                with self.assertRaises(auth_data.AuthDataError):
                    auth_data.prepare_auth_data()
                connect.assert_not_called()


class AuthDataFailureTest(AuthDataTestCase):
    """Ошибки подготовки не оставляют успешный результат или секреты."""

    def test_connection_failure_is_redacted(self) -> None:
        with patch.object(
            auth_data,
            "connect_database",
            side_effect=psycopg.OperationalError("private-value"),  # noqa: WPS226
        ):
            with patch.object(auth_data.logger, "info") as log:
                with self.assertRaises(auth_data.AuthDataError) as caught:
                    auth_data.prepare_auth_data()
        self.assertEqual(
            str(caught.exception),
            "Auth data preparation failed at database connection (OperationalError)",
        )
        self.assertTrue(caught.exception.__suppress_context__)
        log.assert_not_called()

    def test_unreadable_sql_aborts_transaction(self) -> None:
        connection = MagicMock()
        with patch.object(auth_data, "connect_database", return_value=connection):
            with patch.object(Path, "read_text", side_effect=OSError("private-value")):
                with self.assertRaises(auth_data.AuthDataError) as caught:
                    auth_data.prepare_auth_data()
        self.assertEqual(
            str(caught.exception),
            "Auth data preparation failed at 001_first.up.sql (OSError)",
        )
        self.assertEqual(connection.__enter__.return_value.execute.call_count, 2)
        self.assertIs(connection.__exit__.call_args.args[0], OSError)

    def test_commit_failure_is_reported_safely(self) -> None:
        connection = MagicMock()
        connection.__exit__.side_effect = psycopg.OperationalError("private-value")
        with patch.object(auth_data, "connect_database", return_value=connection):
            with self.assertRaises(auth_data.AuthDataError) as caught:
                auth_data.prepare_auth_data()
        message = str(caught.exception)
        self.assertNotIn("private-value", message)
        self.assertIn("OperationalError", message)

    def test_invalid_postgres_settings_are_redacted(self) -> None:
        config = self.root / "invalid.yaml"
        for document in (
            "",
            "postgres: null",
            "postgres: [private-value]",
            "postgres: {password: private-value}",
        ):
            with self.subTest(document=document):
                config.write_text(document)
                with (
                    patch.dict(os.environ, {"PYTEST_CONFIG": str(config)}),
                    patch.object(auth_data.psycopg, "connect") as connect,
                    self.assertRaises(auth_data.AuthDataError) as caught,
                ):
                    auth_data.prepare_auth_data()
                message = str(caught.exception)
                self.assertIn("database connection", message)
                self.assertNotIn("private-value", message)
                connect.assert_not_called()


class AuthDataConnectionTest(AuthDataTestCase):
    """DSN имеет приоритет, пустые настройки используют YAML."""

    def test_explicit_url_bypasses_yaml(self) -> None:
        database_url = "postgresql://localhost/isolated"
        with patch.dict(os.environ, {"TESTDATA_DATABASE_URL": database_url}):
            with patch.object(Path, "read_text") as read:
                with patch.object(auth_data.psycopg, "connect") as connect:
                    self.assertIs(auth_data.connect_database(), connect.return_value)
        read.assert_not_called()
        connect.assert_called_once_with(database_url, connect_timeout=10)

    def test_empty_overrides_use_default_yaml(self) -> None:
        config = self.root / "config.yaml"
        postgres = {
            "host": "db.test",
            "port": 5544,
            "dbname": "isolated",
            "user": "test",
            "password": self.temporary.name,
        }
        config.write_text(auth_data.yaml.safe_dump({"postgres": postgres}))
        settings = {"TESTDATA_DATABASE_URL": "", "PYTEST_CONFIG": ""}
        with (
            patch.object(auth_data, "ROOT", self.root),
            patch.dict(os.environ, settings),
        ):
            with patch.object(auth_data.psycopg, "connect") as connect:
                auth_data.connect_database()
        connect.assert_called_once_with(**postgres, connect_timeout=10)


class AuthEntryPointTestCase(unittest.TestCase):
    """Изолированные переменные окружения для fixture и CLI."""

    def setUp(self) -> None:
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)


class AuthDataEntryPointTest(AuthEntryPointTestCase):
    """Fixture и CLI вызывают один загрузчик."""

    def test_fixture_prepare_and_skip(self) -> None:
        with patch.object(auth_data, "prepare_auth_data") as prepare:  # noqa: WPS226
            unwrap(auth_data.auth_test_data)()
            prepare.assert_called_once_with()
            prepare.reset_mock()
            with patch.dict(os.environ, {"SEED_DATA": "false"}):  # noqa: WPS226
                unwrap(auth_data.auth_test_data)()
            prepare.assert_not_called()

    def test_invalid_setting_and_ci_skip_are_rejected(self) -> None:
        for env in ({"SEED_DATA": "typo"}, {"SEED_DATA": "false", "CI": "true"}):  # noqa: WPS226
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
        with patch.object(
            seed_auth,
            "prepare_auth_data",
            side_effect=auth_data.AuthDataError("bad SQL"),  # noqa: WPS226
        ):
            with redirect_stderr(io.StringIO()) as output:
                self.assertEqual(seed_auth.main(), 1)
            self.assertIn("bad SQL", output.getvalue())


class AuthSeedControlTest(AuthEntryPointTestCase):
    """Флаги подготовки и CI проверяются до обращения к БД."""

    def test_ci_truthy_values_prevent_skip(self) -> None:
        for ci in ("true", "TRUE", "True", "1"):
            with (
                self.subTest(ci=ci),
                patch.dict(os.environ, {"SEED_DATA": "false", "CI": ci}),
                patch.object(auth_data, "prepare_auth_data") as prepare,
            ):
                with self.assertRaisesRegex(
                    auth_data.AuthDataError, "CI requires SEED_DATA=true"
                ):
                    unwrap(auth_data.auth_test_data)()
                prepare.assert_not_called()

    def test_ci_prepares_for_empty_or_true_seed(self) -> None:
        for setting in ("", "true"):
            with (
                self.subTest(setting=setting),
                patch.dict(os.environ, {"SEED_DATA": setting, "CI": "true"}),
            ):
                with patch.object(auth_data, "prepare_auth_data") as prepare:
                    unwrap(auth_data.auth_test_data)()
                    prepare.assert_called_once_with()

    def test_invalid_seed_spellings_never_prepare(self) -> None:
        for setting in ("True", "FALSE", "0", "1", " true "):
            with (
                self.subTest(setting=setting),
                patch.dict(os.environ, {"SEED_DATA": setting}),
                patch.object(auth_data, "prepare_auth_data") as prepare,
            ):
                with self.assertRaisesRegex(
                    auth_data.AuthDataError, "SEED_DATA must be true or false"
                ):
                    unwrap(auth_data.auth_test_data)()
                prepare.assert_not_called()

    def test_fixture_propagates_preparation_failure(self) -> None:
        with patch.object(
            auth_data,
            "prepare_auth_data",
            side_effect=auth_data.AuthDataError("bad SQL"),
        ):
            with self.assertRaisesRegex(auth_data.AuthDataError, "bad SQL"):
                unwrap(auth_data.auth_test_data)()


class AuthSeedCommandTest(AuthEntryPointTestCase):
    """Явная команда всегда применяет данные и разделяет потоки."""

    def test_explicit_cli_ignores_fixture_skip(self) -> None:
        with patch.dict(os.environ, {"SEED_DATA": "false", "CI": "true"}):
            with patch.object(
                seed_auth, "prepare_auth_data", return_value=2
            ) as prepare:
                with (
                    redirect_stdout(io.StringIO()) as output,
                    redirect_stderr(io.StringIO()) as errors,
                ):
                    self.assertEqual(seed_auth.main(), 0)
        prepare.assert_called_once_with()
        self.assertEqual(output.getvalue(), "Auth test data prepared: 2 SQL files\n")
        self.assertEqual(errors.getvalue(), "")

    def test_cli_failure_uses_stderr_only(self) -> None:
        with patch.object(
            seed_auth,
            "prepare_auth_data",
            side_effect=auth_data.AuthDataError("safe failure"),
        ):
            with (
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()) as errors,
            ):
                self.assertEqual(seed_auth.main(), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(errors.getvalue(), "safe failure\n")
