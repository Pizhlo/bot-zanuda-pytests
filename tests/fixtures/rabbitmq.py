import logging
from contextlib import contextmanager
from typing import ContextManager, Generator, Optional

import pika
import pytest

from src.brokers.rabbitmq import RabbitMQ
from src.config import config

logger = logging.getLogger(__name__)

@pytest.fixture(scope="session")
def rabbitmq() -> Generator[RabbitMQ, None, None]:
    """Открывает одно соединение с тестовым RabbitMQ на сессию pytest.

    Контекст RabbitMQ закрывает его после тестов, в том числе при ошибке.
    Отдельные фикстуры управляют своими каналами и очередями; здесь очистки данных нет.
    """
    with RabbitMQ(config.rabbitmq) as rabbitmq:
        yield rabbitmq


@contextmanager
def _get_messages_from_queue(
    rabbitmq: RabbitMQ, queue_name: str
) -> Generator[Optional[bytes], None, None]:
    """Контекстный менеджер для получения сообщений из очереди заметок"""
    if rabbitmq.connection is None:
        raise RuntimeError("RabbitMQ connection is not established")
    channel = rabbitmq.connection.channel()

    try:
        yield _get_single_message(channel, queue_name, rabbitmq.config.queue_poll_attempts)
    finally:
        if channel and not channel.is_closed:
            channel.close()


def _get_single_message(
    channel: pika.channel.Channel, queue_name: str, queue_poll_attempts: int
) -> Optional[bytes]:
    """Получает одно сообщение из очереди, ожидая публикации из auth-service."""
    for attempt in range(queue_poll_attempts):
        method_frame, _header_frame, body = channel.basic_get(
            queue=queue_name, auto_ack=True
        )

        if method_frame:
            logger.info("Received message: %s", body)
            return body if isinstance(body, bytes) else None

    logger.info("No messages in queue")
    return None


@pytest.fixture(scope="function")
def note_messages_from_rabbitmq(
    rabbitmq: RabbitMQ,
) -> ContextManager[Optional[bytes]]:
    """Фикстура, возвращающая сообщение из очереди заметок"""

    return _get_messages_from_queue(rabbitmq, rabbitmq.config.notes_queue)


@pytest.fixture(scope="function")
def auth_service_error_messages_from_rabbitmq(
    rabbitmq: RabbitMQ,
) -> ContextManager[Optional[bytes]]:
    """Готовит очередь ошибок для одного сценария на сохраняемом тестовом стенде.

    Остатки предыдущего неудачного теста не должны подменять ожидаемый audit event.
    Очистка выполняется при получении фикстуры, до HTTP-запроса теста. Другие очереди
    не затрагиваются; параллельные сценарии с общей очередью не поддерживаются.
    """
    if rabbitmq.connection is None:
        raise RuntimeError("RabbitMQ connection is not established")
    channel = rabbitmq.connection.channel()
    try:
        channel.queue_purge(queue=rabbitmq.config.auth_service_error_queue)
    finally:
        channel.close()
    return _get_messages_from_queue(rabbitmq, rabbitmq.config.auth_service_error_queue)
