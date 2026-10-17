"""Проверки webserver seed без БД и пользовательского YAML."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from inspect import unwrap
from pathlib import Path
from unittest.mock import patch

from tests.fixtures import webserver_data
from tests.fixtures.auth_data import AuthDataError
from tools import seed_webserver


class WebserverDataTest(unittest.TestCase):
    """Защищает выбор SQL, локальный skip и самостоятельную команду."""

    def test_default_sources(self) -> None:
        """Набор webserver выбирается без вмешательства в auth SQL."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(webserver_data, "prepare_sql_data", return_value=1) as loader:
                self.assertEqual(webserver_data.prepare_webserver_data(), 1)
                self.assertIn("testdata/webserver", str(loader.call_args.args[0][0]))

    def test_missing_sources(self) -> None:
        """Пустой каталог отклоняется до подключения к БД."""
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"TESTDATA_PATH": folder}):
                with self.assertRaises(AuthDataError):
                    webserver_data.prepare_webserver_data()

    def test_custom_sources(self) -> None:
        """Override выбирает только up-файлы в порядке имени."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "002.up.sql").write_text("SELECT 2")
            (root / "001.up.sql").write_text("SELECT 1")
            (root / "001.down.sql").write_text("never")
            with patch.dict(os.environ, {"TESTDATA_PATH": folder}):
                with patch.object(webserver_data, "prepare_sql_data", return_value=2) as loader:
                    self.assertEqual(webserver_data.prepare_webserver_data(), 2)
                    self.assertEqual([source.name for source in loader.call_args.args[0]],
                                     ["001.up.sql", "002.up.sql"])

    def test_fixture_modes(self) -> None:
        """Fixture готовит по умолчанию, пропускает локально и запрещает skip в CI."""
        fixture = unwrap(webserver_data.webserver_test_data)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(webserver_data, "prepare_webserver_data") as loader:
                fixture()
                loader.assert_called_once()
                loader.reset_mock()
                os.environ["SEED_DATA"] = "false"
                fixture()
                loader.assert_not_called()
                os.environ["CI"] = "true"
                with self.assertRaisesRegex(AuthDataError, "CI requires"):
                    fixture()
                os.environ["SEED_DATA"] = "invalid"
                with self.assertRaisesRegex(AuthDataError, "must be"):
                    fixture()

    def test_standalone_success_and_failure(self) -> None:
        """CLI возвращает результат loader и безопасную ошибку."""
        with redirect_stdout(io.StringIO()):
            with patch.object(seed_webserver, "prepare_webserver_data", return_value=1):
                self.assertEqual(seed_webserver.main(), 0)
        with redirect_stderr(io.StringIO()):
            with patch.object(seed_webserver, "prepare_webserver_data",
                              side_effect=AuthDataError("failed")):
                self.assertEqual(seed_webserver.main(), 1)
