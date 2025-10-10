"""
Конфигурация для тестов
"""

from pydantic import AnyUrl, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

API_TIMEOUT = 30


class WebServerConfig(BaseSettings):
    """Конфигурация для веб-сервера"""

    base_url: AnyUrl = Field(default=AnyUrl("http://localhost:8080"))
    timeout: int = Field(default=API_TIMEOUT)


class Config(BaseSettings):
    """Конфигурация для тестов"""

    # Базовые настройки
    webserver: WebServerConfig = Field(default_factory=WebServerConfig)

    model_config = SettingsConfigDict(
        yaml_file="config.yaml", env_file_encoding="utf-8", extra="ignore"
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
        return (YamlConfigSettingsSource(settings_cls),)


# Глобальный экземпляр конфигурации
config = Config()
