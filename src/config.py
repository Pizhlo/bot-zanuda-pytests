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
RABBITMQ_DEFAULT_PORT = 5672
DEFAULT_POSTGRES_PORT = 5432
DEFAULT_HEARTBEAT = 300
DEFAULT_BLOCKED_CONNECTION_TIMEOUT = 300
DEFAULT_CONNECTION_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 5


class WebServerConfig(BaseSettings):
    """Конфигурация для веб-сервера"""

    base_url: AnyUrl = Field(default=AnyUrl("http://localhost:8080"))
    timeout: int = Field(default=API_TIMEOUT)

class AuthServiceConfig(BaseSettings):
    """Конфигурация для сервиса авторизации"""

    base_url: AnyUrl = Field(default=AnyUrl("http://localhost:8080"))
    timeout: int = Field(default=API_TIMEOUT)
    secret_key: str = Field()

_DEFAULT_QUEUE_POLL_ATTEMPTS = 30

class RabbitMQConfig(BaseSettings):
    """Конфигурация для RabbitMQ"""

    host: str = Field(default="localhost")
    port: int = Field(default=RABBITMQ_DEFAULT_PORT)
    username: str = Field(default="guest")
    password: str = Field(default="guest")
    virtual_host: str = Field(default="/")
    notes_queue: str = Field(default="notes")
    notes_exchange: str = Field(default="notes")
    heartbeat: int = Field(default=DEFAULT_HEARTBEAT)
    blocked_connection_timeout: int = Field(default=DEFAULT_BLOCKED_CONNECTION_TIMEOUT)
    connection_attempts: int = Field(default=DEFAULT_CONNECTION_ATTEMPTS)
    retry_delay: int = Field(default=DEFAULT_RETRY_DELAY)
    auth_service_error_queue: str = Field(default="errors.auth-service")
    queue_poll_attempts: int = Field(default=_DEFAULT_QUEUE_POLL_ATTEMPTS)


class VaultConfig(BaseSettings):
    """Конфигурация для HashiCorp Vault."""

    base_url: AnyUrl = Field(default=AnyUrl("http://localhost:8200"))
    token: str = Field(default="root")
    timeout: int = Field(default=API_TIMEOUT)
    mount_point: str = Field(default="secret")
    auth_clients_path: str = Field(default="auth/clients")


class PostgresConfig(BaseSettings):
    """Конфигурация для PostgreSQL."""

    host: str = Field(default="localhost")
    port: int = Field(default=DEFAULT_POSTGRES_PORT)
    user: str = Field(default="postgres")
    password: str = Field(default="postgres")
    dbname: str = Field(default="postgres")


class Config(BaseSettings):
    """Конфигурация для тестов"""

    # Базовые настройки
    webserver: WebServerConfig = Field(default_factory=WebServerConfig)
    rabbitmq: RabbitMQConfig = Field(default_factory=RabbitMQConfig)
    vault: VaultConfig = Field(default_factory=VaultConfig)
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    auth_service: AuthServiceConfig

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
config = Config()  # type: ignore[call-arg]
