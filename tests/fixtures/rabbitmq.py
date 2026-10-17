import logging
import time
from contextlib import closing, contextmanager
from typing import ContextManager, Generator, Optional

import pika
import pytest

from src.brokers.rabbitmq import RabbitMQ
from src.config import config

logger = logging.getLogger(__name__)
_CONNECTION_MISSING = "RabbitMQ connection is not established"
NoteMessage = ContextManager[Optional[bytes]]

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
        raise RuntimeError(_CONNECTION_MISSING)
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


def _poll_note(
    channel: pika.channel.Channel, rabbitmq: RabbitMQ,
) -> tuple[int | None, bytes | None]:
    """Ожидает сообщение ограниченное время без автоматического подтверждения."""
    for _ in range(rabbitmq.config.queue_poll_attempts):
        frame, _header, body = channel.basic_get(
            queue=rabbitmq.config.notes_queue, auto_ack=False,
        )
        if frame:
            return frame.delivery_tag, body if isinstance(body, bytes) else None
        time.sleep(0.1)
    return None, None


@contextmanager
def _note_message(rabbitmq: RabbitMQ) -> Generator[Optional[bytes], None, None]:
    """Подтверждает сообщение только после assertions внутри with-блока теста."""
    if rabbitmq.connection is None:
        raise RuntimeError(_CONNECTION_MISSING)
    with closing(rabbitmq.connection.channel()) as channel:
        delivery_tag, body = _poll_note(channel, rabbitmq)
        yield body
        if delivery_tag is not None:
            channel.basic_ack(delivery_tag=delivery_tag)


@pytest.fixture(scope="function")
def note_messages_from_rabbitmq(rabbitmq: RabbitMQ) -> Generator[NoteMessage, None, None]:
    """Очищает только notes перед запросом и после сценария, включая ошибку."""
    if rabbitmq.connection is None:
        raise RuntimeError(_CONNECTION_MISSING)
    with closing(rabbitmq.connection.channel()) as channel:
        channel.queue_purge(queue=rabbitmq.config.notes_queue)
        try:
            yield _note_message(rabbitmq)
        finally:
            channel.queue_purge(queue=rabbitmq.config.notes_queue)


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
        raise RuntimeError(_CONNECTION_MISSING)
    channel = rabbitmq.connection.channel()
    try:
        channel.queue_purge(queue=rabbitmq.config.auth_service_error_queue)
    finally:
        channel.close()
    return _get_messages_from_queue(rabbitmq, rabbitmq.config.auth_service_error_queue)
