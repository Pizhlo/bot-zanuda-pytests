"""Проверки выбора YAML без пользовательского config.yaml и внешних сервисов."""

import importlib
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError
import yaml


class ConfiguredTestCase(unittest.TestCase):
    """Создаёт изолированный YAML с одноразовым тестовым ключом."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config_path = self.root / "config.yaml"
        self.secret = secrets.token_hex()
        self.config_path.write_text(
            yaml.safe_dump(
                {
                    "auth_service": {"secret_key": self.secret},
                }
            )
        )
        environment = patch.dict(
            os.environ,
            {
                "PYTEST_CONFIG": str(self.config_path),  # noqa: WPS226
            },
            clear=True,
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.config_module = importlib.import_module("src.config")
        self.settings = self.config_module.Config()

    def use_working_directory(self, directory: Path) -> None:
        """Восстанавливает cwd до удаления временного каталога."""
        original = Path.cwd()
        os.chdir(directory)
        self.addCleanup(os.chdir, original)


class ConfigSelectionTest(ConfiguredTestCase):
    """YAML выбирается при создании Config, старые конфиги остаются допустимыми."""

    def test_missing_openfga_section_uses_defaults(self) -> None:
        self.assertEqual(str(self.settings.openfga.base_url), "http://localhost:8081/")
        self.assertEqual(self.settings.openfga.store_name, "bot-zanuda")
        self.assertEqual(self.settings.openfga.timeout, self.config_module.API_TIMEOUT)
        self.assertEqual(self.settings.auth_service.secret_key, self.secret)

    def test_custom_yaml_overrides_service_settings(self) -> None:
        custom = self.root / "selected.yaml"
        custom.write_text(
            yaml.safe_dump(
                {
                    "auth_service": {
                        "secret_key": self.secret,
                        "base_url": "http://auth.test:9000",
                    },
                    "openfga": {
                        "base_url": "http://fga.test:9001/prefix/",
                        "store_name": "isolated",
                        "timeout": 7,
                    },
                }
            )
        )
        with patch.dict(os.environ, {"PYTEST_CONFIG": str(custom)}):
            selected = self.config_module.Config()
        self.assertEqual(str(selected.auth_service.base_url), "http://auth.test:9000/")
        self.assertEqual(str(selected.openfga.base_url), "http://fga.test:9001/prefix/")
        self.assertEqual(selected.openfga.store_name, "isolated")
        self.assertEqual(selected.openfga.timeout, 7)

    def test_empty_selector_uses_local_yaml(self) -> None:
        self.use_working_directory(self.root)
        for selector in (None, ""):
            with (
                self.subTest(selector=selector),
                patch.dict(os.environ, {}, clear=True),
            ):
                if selector is not None:
                    os.environ["PYTEST_CONFIG"] = selector
                selected = self.config_module.Config()
                self.assertEqual(selected.auth_service.secret_key, self.secret)

    def test_relative_selector_uses_cwd(self) -> None:
        self.use_working_directory(self.root.parent)
        relative = str(self.config_path.relative_to(self.root.parent))
        with patch.dict(os.environ, {"PYTEST_CONFIG": relative}):
            selected = self.config_module.Config()
        self.assertEqual(selected.auth_service.secret_key, self.secret)

    def test_missing_yaml_never_uses_local_fallback(self) -> None:
        self.use_working_directory(self.root)
        with patch.dict(os.environ, {"PYTEST_CONFIG": str(self.root / "missing.yaml")}):
            with self.assertRaises(ValidationError):
                self.config_module.Config()

    def test_invalid_openfga_url_is_rejected(self) -> None:
        self.config_path.write_text(
            yaml.safe_dump(
                {
                    "auth_service": {"secret_key": self.secret},
                    "openfga": {"base_url": "not a URL"},
                }
            )
        )
        with self.assertRaises(ValidationError):
            self.config_module.Config()
