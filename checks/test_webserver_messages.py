"""Проверки notes fixture: очередь, ожидание, подтверждение и cleanup."""

import os
import tempfile
import unittest
from inspect import unwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

# Runtime config is loaded during import; unit checks must not use developer YAML.
with tempfile.TemporaryDirectory() as config_dir:
    config_path = Path(config_dir) / "pytest.yaml"
    config_path.write_text("auth_service:\n  secret_key: unit-test-only\n")
    with patch.dict(os.environ, {"PYTEST_CONFIG": str(config_path)}):
        from tests.fixtures import rabbitmq


class WebserverMessagesTest(unittest.TestCase):
    """Не использует настоящий брокер; проверяет границы одного сценария."""

    def broker(self) -> MagicMock:
        """Создаёт mock канала с одним сообщением."""
        broker = MagicMock()
        broker.config.notes_queue = "notes"
        broker.config.queue_poll_attempts = 2
        channel = broker.connection.channel.return_value
        channel.basic_get.return_value = (
            MagicMock(delivery_tag=1), None, b"message",
        )
        return broker

    def test_ack_after_validation(self) -> None:
        """Ack происходит после выхода из блока с assertions."""
        broker = self.broker()
        channel = broker.connection.channel.return_value
        with rabbitmq._note_message(broker) as body:
            self.assertEqual(body, b"message")
            channel.basic_ack.assert_not_called()
        channel.basic_ack.assert_called_once_with(delivery_tag=1)
        channel.close.assert_called_once()

    def test_no_ack_on_validation_failure(self) -> None:
        """Неверное сообщение не подтверждается, канал закрывается."""
        broker = self.broker()
        with self.assertRaises(AssertionError):
            with rabbitmq._note_message(broker):
                raise AssertionError("invalid payload")
        channel = broker.connection.channel.return_value
        channel.basic_ack.assert_not_called()
        channel.close.assert_called_once()

    def test_timeout_and_invalid_body(self) -> None:
        """Пустая очередь имеет ограниченное число опросов с паузами."""
        broker = self.broker()
        channel = broker.connection.channel.return_value
        channel.basic_get.return_value = (None, None, None)
        with patch.object(rabbitmq.time, "sleep") as sleep:
            with rabbitmq._note_message(broker) as body:
                self.assertIsNone(body)
            self.assertEqual(sleep.call_count, 2)
        channel.basic_get.return_value = (MagicMock(delivery_tag=1), None, "not bytes")
        with rabbitmq._note_message(broker) as body:
            self.assertIsNone(body)

    def test_fixture_purges_before_and_after(self) -> None:
        """Сценарий получает пустую notes-очередь, исключение не отменяет уборку."""
        broker = self.broker()
        fixture = unwrap(rabbitmq.note_messages_from_rabbitmq)(broker)
        next(fixture)
        channel = broker.connection.channel.return_value
        channel.queue_purge.assert_called_once_with(queue="notes")
        fixture.close()
        self.assertEqual(channel.queue_purge.call_count, 2)
        channel.close.assert_called_once()

    def test_missing_connection(self) -> None:
        """Отсутствующее соединение диагностируется до работы с каналом."""
        broker = self.broker()
        broker.connection = None
        with self.assertRaisesRegex(RuntimeError, "not established"):
            with rabbitmq._note_message(broker):
                self.fail("missing connection entered context")
        with self.assertRaisesRegex(RuntimeError, "not established"):
            next(unwrap(rabbitmq.note_messages_from_rabbitmq)(broker))
