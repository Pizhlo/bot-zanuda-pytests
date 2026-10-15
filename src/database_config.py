"""Общий YAML-источник PostgreSQL для тестов и самостоятельной подготовки данных.

Здесь нет глобального Config и настроек HTTP-клиентов: SQL можно применить с одним
разделом postgres. Полный Config наследует этот источник, чтобы путь к файлу,
проверка значений и defaults никогда не расходились с загрузчиком данных.
"""

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

DEFAULT_POSTGRES_PORT = 5432


class PostgresConfig(BaseSettings):
    """Параметры БД с прежними defaults и валидацией для всех её потребителей."""

    host: str = Field(default="localhost")
    port: int = Field(default=DEFAULT_POSTGRES_PORT)
    user: str = Field(default="postgres")
    password: str = Field(default="postgres")
    dbname: str = Field(default="postgres")


class DatabaseConfig(BaseSettings):
    """Читает только PostgreSQL, позволяя seed обойтись без настроек сервиса.

    Полный Config расширяет эту модель остальными секциями. Неизвестные секции
    YAML игнорируются здесь, но проверяются полным Config при запуске тестов.
    Пропущенные поля и секция postgres получают одинаковые значения по умолчанию.
    """

    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    model_config = SettingsConfigDict(
        yaml_file="config.yaml", env_file_encoding="utf-8", extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Выбирает один YAML для Config и seed относительно рабочего каталога.

        Runner передаёт явный PYTEST_CONFIG; прямой pytest и seed используют
        config.yaml из cwd. Проверяем наличие файла до создания YAML-источника:
        Pydantic иначе пропустит отсутствующий файл, и seed подключится по defaults
        вместо указанной пользователем БД. Реквизиты и содержимое YAML не выводятся.
        """
        path = Path(os.environ.get("PYTEST_CONFIG") or "config.yaml")
        if not path.is_file():
            raise FileNotFoundError("Test configuration file does not exist or is not a file")
        return (YamlConfigSettingsSource(settings_cls, yaml_file=path),)
