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
        yield _get_single_message(channel, queue_name)
    finally:
        if channel and not channel.is_closed:
            channel.close()


def _get_single_message(
    channel: pika.channel.Channel, queue_name: str
) -> Optional[bytes]:
    """Получает одно сообщение из очереди"""
    # Получаем одно сообщение без блокировки из существующей очереди
    method_frame, _header_frame, body = channel.basic_get(
        queue=queue_name, auto_ack=True
    )

    if method_frame:
        logger.info("Received message: %s", body)
        return body if isinstance(body, bytes) else None
    else:
        logger.info("No messages in queue")
        return None


@pytest.fixture(scope="function")
def note_messages_from_rabbitmq(
    rabbitmq: RabbitMQ,
) -> ContextManager[Optional[bytes]]:
    """Фикстура, возвращающая сообщение из очереди заметок"""

    return _get_messages_from_queue(rabbitmq, rabbitmq.config.notes_queue)
