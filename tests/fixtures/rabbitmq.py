import logging
import time
from collections.abc import Callable
from functools import partial
from contextlib import closing, contextmanager
from typing import ContextManager, Generator, Optional

import pika
import pytest

from src.brokers.rabbitmq import RabbitMQ
from src.config import config

logger = logging.getLogger(__name__)
_CONNECTION_MISSING = "RabbitMQ connection is not established"
QueueMessage = ContextManager[Optional[bytes]]

@pytest.fixture(scope="session")
def rabbitmq() -> Generator[RabbitMQ, None, None]:
    """Открывает одно соединение с тестовым RabbitMQ на сессию pytest.

    Контекст RabbitMQ закрывает его после тестов, в том числе при ошибке.
    Отдельные фикстуры управляют своими каналами и очередями; здесь очистки данных нет.
    """
    with RabbitMQ(config.rabbitmq) as rabbitmq:
        yield rabbitmq


def _poll_delivery(
    channel: pika.channel.Channel, queue_name: str, attempts: int,
) -> tuple[int | None, bytes | None]:
    """Ожидает сообщение ограниченное время без автоматического подтверждения."""
    deadline = time.monotonic() + 0.1 * attempts
    for _ in range(attempts):
        if time.monotonic() >= deadline:
            break
        frame, _header, body = channel.basic_get(
            queue=queue_name, auto_ack=False,
        )
        if frame:
            return frame.delivery_tag, body if isinstance(body, bytes) else None
        remaining = max(0, deadline - time.monotonic())
        time.sleep(min(0.1, remaining))
    return None, None


@contextmanager
def _note_message(rabbitmq: RabbitMQ) -> Generator[Optional[bytes], None, None]:
    """Подтверждает сообщение только после assertions внутри with-блока теста."""
    if rabbitmq.connection is None:
        raise RuntimeError(_CONNECTION_MISSING)
    with closing(rabbitmq.connection.channel()) as channel:
        delivery_tag, body = _poll_delivery(channel, rabbitmq.config.notes_queue, rabbitmq.config.queue_poll_attempts)
        yield body
        if delivery_tag is not None:
            channel.basic_ack(delivery_tag=delivery_tag)


@pytest.fixture(scope="function")
def note_messages_from_rabbitmq(rabbitmq: RabbitMQ) -> Generator[QueueMessage, None, None]:
    """Очищает только notes перед запросом и после сценария, включая ошибку."""
    if rabbitmq.connection is None:
        raise RuntimeError(_CONNECTION_MISSING)
    with closing(rabbitmq.connection.channel()) as channel:
        channel.queue_purge(queue=rabbitmq.config.notes_queue)
        try:
            yield _note_message(rabbitmq)
        finally:
            channel.queue_purge(queue=rabbitmq.config.notes_queue)


@contextmanager
def _audit_delivery(rabbitmq: RabbitMQ) -> Generator[Optional[bytes], None, None]:
    """Подтверждает событие после проверки тестом и обнаруживает второй ответ на тот же запрос."""
    if rabbitmq.connection is None:
        raise RuntimeError(_CONNECTION_MISSING)
    queue = rabbitmq.config.auth_service_error_queue
    with closing(rabbitmq.connection.channel()) as channel:
        delivery_tag, body = _poll_delivery(channel, queue, rabbitmq.config.queue_poll_attempts)
        yield body
        duplicate, _ = _poll_delivery(channel, queue, min(3, rabbitmq.config.queue_poll_attempts))
        assert duplicate is None, "В очереди аудита больше одного события"
        if delivery_tag is not None:
            channel.basic_ack(delivery_tag=delivery_tag)


type AuditStream = Callable[[], QueueMessage]


@pytest.fixture()
def audit_stream(rabbitmq: RabbitMQ) -> Generator[AuditStream, None, None]:
    """Изолирует очередь ошибок на время одного последовательного HTTP-сценария.

    Выделенная очередь пуста до запроса. После теста убирает и сообщение,
    которое успело прийти до упавшей проверки HTTP-ответа.
    """
    if rabbitmq.connection is None:
        raise RuntimeError(_CONNECTION_MISSING)
    with closing(rabbitmq.connection.channel()) as channel:
        channel.queue_purge(queue=rabbitmq.config.auth_service_error_queue)
        try:
            yield partial(_audit_delivery, rabbitmq)
        finally:
            channel.queue_purge(queue=rabbitmq.config.auth_service_error_queue)


@pytest.fixture()
def auth_service_error_messages_from_rabbitmq(audit_stream: AuditStream) -> QueueMessage:
    """Открывает чтение одного события, проверяемого внутри with-блока теста."""
    return audit_stream()
