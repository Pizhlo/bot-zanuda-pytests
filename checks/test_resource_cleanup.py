"""Изоляция ресурсов и audit-очереди без запуска auth-service и RabbitMQ."""

from dataclasses import asdict, replace
import importlib
from inspect import unwrap
from unittest.mock import MagicMock, patch
import uuid

import httpx
import pika

from checks.test_config import ConfiguredTestCase


class RabbitMQAuditCleanupTest(ConfiguredTestCase):
    """Очередь очищается до запроса, а служебный канал закрывается при ошибках."""

    def setUp(self) -> None:
        super().setUp()
        self.module = importlib.import_module("tests.fixtures.rabbitmq")
        self.broker = MagicMock()
        self.broker.config.auth_service_error_queue = "errors.isolated"
        self.broker.config.queue_poll_attempts = 1

    def test_purges_only_audit_queue_before_consuming(self) -> None:
        purge_channel = MagicMock()
        read_channel = MagicMock()
        read_channel.is_closed = False
        read_channel.basic_get.return_value = (object(), None, b"current-event")
        self.broker.connection.channel.side_effect = [purge_channel, read_channel]
        messages = unwrap(self.module.auth_service_error_messages_from_rabbitmq)(
            self.broker
        )
        purge_channel.queue_purge.assert_called_once_with(queue="errors.isolated")
        purge_channel.close.assert_called_once_with()
        self.assertEqual(self.broker.connection.channel.call_count, 1)
        read_channel.basic_get.assert_not_called()
        with messages as body:
            self.assertEqual(body, b"current-event")
        read_channel.queue_purge.assert_not_called()
        read_channel.basic_get.assert_called_once_with(
            queue="errors.isolated", auto_ack=True
        )
        read_channel.close.assert_called_once_with()

    def test_missing_connection_prevents_consumption(self) -> None:
        self.broker.connection = None
        with self.assertRaisesRegex(RuntimeError, "connection is not established"):
            unwrap(self.module.auth_service_error_messages_from_rabbitmq)(self.broker)

    def test_failed_purge_closes_channel(self) -> None:
        channel = self.broker.connection.channel.return_value
        channel.queue_purge.side_effect = pika.exceptions.AMQPError("purge failed")
        with self.assertRaises(pika.exceptions.AMQPError):
            unwrap(self.module.auth_service_error_messages_from_rabbitmq)(self.broker)
        channel.close.assert_called_once_with()
        channel.basic_get.assert_not_called()
        self.broker.connection.channel.assert_called_once_with()


class IsolatedResourceTest(ConfiguredTestCase):
    """Сценарии 200/409 подготавливаются независимо и очищаются после ошибок."""

    def setUp(self) -> None:
        super().setUp()
        self.module = importlib.import_module("tests.auth_service.api.v0.test_resource")
        self.client = MagicMock()
        self.client.update_resource.return_value = httpx.Response(httpx.codes.OK)
        self.openfga = MagicMock()
        self.case = self.module.UpdateResourceCase(
            request=self.module.DEFAULT_UPDATE_RESOURCE_REQUEST,
            expected_status_code=httpx.codes.OK,
            expected_response=None,
            expected_message=None,
            x_telegram_user_id="isolated-user",
        )
        self.cleanup = MagicMock()
        cleanup = patch.object(self.module, "remove_resource_relations", self.cleanup)
        cleanup.start()
        self.addCleanup(cleanup.stop)

    def test_success_cleans_only_its_resource(self) -> None:
        for kind in ("note", "space", "reminder"):
            with self.subTest(kind=kind):
                resource_id = str(uuid.uuid4())
                ref = self.module.resource.ResourceRef(type=kind, id=resource_id)
                case = replace(
                    self.case, request=replace(self.case.request, resource=ref)
                )
                fixture = unwrap(self.module.isolated_resource)(
                    case, self.secret, self.client, self.openfga
                )
                self.addCleanup(fixture.close)
                next(fixture)
                self.cleanup.assert_not_called()
                self.client.update_resource.assert_not_called()
                with self.assertRaises(StopIteration):
                    next(fixture)
                self.cleanup.assert_called_once_with(self.openfga, f"{kind}:{ref.id}")
                self.cleanup.reset_mock()

    def test_conflict_prepares_independent_request(self) -> None:
        case = replace(self.case, expected_status_code=httpx.codes.CONFLICT)
        original = asdict(case.request)
        fixture = unwrap(self.module.isolated_resource)(
            case, self.secret, self.client, self.openfga
        )
        self.addCleanup(fixture.close)
        next(fixture)
        self.client.update_resource.assert_called_once()
        update_call = self.client.update_resource.call_args
        submitted = update_call.args[0]
        self.assertNotEqual(submitted["request_id"], original["request_id"])  # noqa: WPS226
        self.assertEqual({**submitted, "request_id": original["request_id"]}, original)
        self.assertEqual(
            update_call.kwargs,
            {
                "token": self.secret,
                "x_telegram_user_id": case.x_telegram_user_id,
            },
        )
        self.assertEqual(asdict(case.request), original)
        fixture.close()
        self.cleanup.assert_called_once_with(self.openfga, self.module.NOTE_RESOURCE)

    def test_failed_scenario_still_cleans_resource(self) -> None:
        fixture = unwrap(self.module.isolated_resource)(
            self.case, self.secret, self.client, self.openfga
        )
        self.addCleanup(fixture.close)
        next(fixture)
        failure = AssertionError("scenario failed")
        with self.assertRaises(AssertionError) as caught:
            fixture.throw(failure)
        self.assertIs(caught.exception, failure)  # noqa: WPS441
        self.cleanup.assert_called_once_with(self.openfga, self.module.NOTE_RESOURCE)

    def test_rejected_requests_never_change_relations(self) -> None:
        for status in (400, 401, 403, 404, 500):
            with self.subTest(status=status):
                case = replace(self.case, expected_status_code=status)
                fixture = unwrap(self.module.isolated_resource)(
                    case, self.secret, self.client, self.openfga
                )
                self.addCleanup(fixture.close)
                next(fixture)
                with self.assertRaises(StopIteration):
                    next(fixture)
                self.client.update_resource.assert_not_called()
                self.cleanup.assert_not_called()

    def test_failed_preparation_blocks_scenario(self) -> None:
        self.client.update_resource.return_value = httpx.Response(
            httpx.codes.BAD_REQUEST, text="preparation rejected"
        )
        case = replace(self.case, expected_status_code=httpx.codes.CONFLICT)
        fixture = unwrap(self.module.isolated_resource)(
            case, self.secret, self.client, self.openfga
        )
        self.addCleanup(fixture.close)
        with self.assertRaisesRegex(AssertionError, "preparation rejected"):
            next(fixture)
        self.client.update_resource.assert_called_once()
