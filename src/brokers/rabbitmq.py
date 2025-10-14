import logging
from typing import Any, Optional

import pika

from src.config import RabbitMQConfig

logger = logging.getLogger(__name__)


class RabbitMQ:
    def __init__(self, config: RabbitMQConfig) -> None:
        self.config = config
        self.connection: Optional[pika.BlockingConnection] = None

    def __enter__(self) -> "RabbitMQ":
        """Поддержка контекстного менеджера - вход"""
        credentials = pika.PlainCredentials(
            username=self.config.username, password=self.config.password
        )
        connection_params = pika.ConnectionParameters(
            host=self.config.host, 
            port=self.config.port, 
            credentials=credentials,
            virtual_host=self.config.virtual_host,
            heartbeat=self.config.heartbeat,
            blocked_connection_timeout=self.config.blocked_connection_timeout,
            connection_attempts=self.config.connection_attempts,
            retry_delay=self.config.retry_delay,
        )
        self.connection = pika.BlockingConnection(connection_params)
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        """Поддержка контекстного менеджера - выход"""
        if self.connection is not None and not self.connection.is_closed:
            self.connection.close()
