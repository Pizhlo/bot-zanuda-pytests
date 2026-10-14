"""Проверки адресной очистки OpenFGA через HTTP transport в памяти."""

import importlib
from inspect import unwrap
import json
from unittest.mock import patch

import httpx

from checks.test_config import ConfiguredTestCase


class OpenFGATestCase(ConfiguredTestCase):
    """Проверяет выбор store, точные удаления и отказ от частичной очистки."""

    def setUp(self) -> None:
        super().setUp()
        self.module = importlib.import_module("tests.fixtures.openfga")
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response] = []
        self.client = httpx.Client(
            base_url="http://fga.test/stores/test-store/",
            transport=httpx.MockTransport(self.respond),
        )
        self.addCleanup(self.client.close)
        configuration = patch.object(self.module, "config", self.settings)
        configuration.start()
        self.addCleanup(configuration.stop)

    def respond(self, request: httpx.Request) -> httpx.Response:
        """Неожиданный запрос без подготовленного ответа завершает проверку."""
        self.requests.append(request)
        return self.responses.pop(0)


class OpenFGAStoreTest(OpenFGATestCase):
    """Открывается только единственное выбранное хранилище."""

    def test_fixture_selects_store_and_closes_client(self) -> None:
        self.responses = [
            httpx.Response(
                httpx.codes.OK,
                json={
                    "stores": [  # noqa: WPS226
                        {"id": "other-store", "name": "other"},  # noqa: WPS226
                        {"id": "test-store", "name": self.settings.openfga.store_name},
                    ]
                },
            )
        ]
        self.client.base_url = str(self.settings.openfga.base_url)
        fixture = unwrap(self.module.openfga)()
        self.addCleanup(fixture.close)
        with patch.object(
            self.module.httpx, "Client", return_value=self.client
        ) as factory:
            selected = next(fixture)
            factory.assert_called_once_with(
                base_url=str(self.settings.openfga.base_url),
                timeout=self.settings.openfga.timeout,
            )
        self.assertIs(selected, self.client)
        self.assertEqual(
            str(selected.base_url), "http://localhost:8081/stores/test-store/"
        )
        self.assertEqual(self.requests[0].url.path, "/stores")
        query = dict(self.requests[0].url.params)
        self.assertEqual(query, {"name": "bot-zanuda"})
        fixture.close()
        self.assertTrue(self.client.is_closed)

    def test_fixture_rejects_unsafe_store_selection(self) -> None:
        store = {"id": "test-store", "name": self.settings.openfga.store_name}
        payloads: tuple[dict[str, object], ...] = (
            {"stores": []},
            {"stores": [{"id": "other", "name": "other"}]},
            {"stores": [store, {**store, "id": "duplicate"}]},
            {"stores": [store], "continuation_token": "next-page"},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                client = httpx.Client(
                    transport=httpx.MockTransport(self.respond),
                    base_url="http://fga.test",
                )
                self.addCleanup(client.close)
                self.responses = [httpx.Response(httpx.codes.OK, json=payload)]
                with (
                    patch.object(self.module.httpx, "Client", return_value=client),
                    self.assertRaisesRegex(
                        AssertionError, "Expected one test OpenFGA store"
                    ),
                ):
                    next(unwrap(self.module.openfga)())
                self.assertTrue(client.is_closed)

    def test_listing_failure_closes_client(self) -> None:
        self.responses = [httpx.Response(httpx.codes.SERVICE_UNAVAILABLE)]
        with patch.object(self.module.httpx, "Client", return_value=self.client):
            with self.assertRaises(httpx.HTTPStatusError):
                next(unwrap(self.module.openfga)())
        self.assertTrue(self.client.is_closed)
        self.assertEqual(len(self.requests), 1)


class OpenFGACleanupTest(OpenFGATestCase):
    """Очистка использует точные связи и сообщает о неполном результате."""

    def test_cleanup_deletes_only_resource_keys(self) -> None:
        keys = [
            {"user": "user:owner", "relation": "owner", "object": "note:created"},  # noqa: WPS226
            {"user": "space:parent", "relation": "parent", "object": "note:created"},
        ]
        self.responses = [
            httpx.Response(
                httpx.codes.OK,
                json={"tuples": [{"key": key, "timestamp": "ignored"} for key in keys]},  # noqa: WPS226
            ),
            httpx.Response(httpx.codes.OK, json={}),
        ]
        self.module.remove_resource_relations(self.client, "note:created")
        self.assertEqual(
            [request.method for request in self.requests], ["POST", "POST"]
        )
        self.assertEqual(
            [request.url.path for request in self.requests],
            [
                "/stores/test-store/read",
                "/stores/test-store/write",
            ],
        )
        self.assertEqual(
            json.loads(self.requests[0].content),
            {
                "tuple_key": {"object": "note:created"},
                "consistency": "HIGHER_CONSISTENCY",
            },
        )
        self.assertEqual(
            json.loads(self.requests[1].content), {"deletes": {"tuple_keys": keys}}
        )

    def test_absent_resource_does_not_write(self) -> None:
        self.responses = [
            httpx.Response(
                httpx.codes.OK, json={"tuples": [], "continuation_token": ""}
            )
        ]
        self.module.remove_resource_relations(self.client, "note:absent")
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].url.path, "/stores/test-store/read")

    def test_paginated_read_never_deletes(self) -> None:
        self.responses = [
            httpx.Response(
                httpx.codes.OK,
                json={
                    "tuples": [
                        {
                            "key": {
                                "user": "user:owner",
                                "relation": "owner",
                                "object": "note:created",
                            }
                        }
                    ],
                    "continuation_token": "next-page",
                },
            )
        ]
        with self.assertRaisesRegex(AssertionError, "Unexpected pagination"):
            self.module.remove_resource_relations(self.client, "note:created")
        self.assertEqual(len(self.requests), 1)

    def test_failed_read_does_not_attempt_delete(self) -> None:
        self.responses = [httpx.Response(httpx.codes.INTERNAL_SERVER_ERROR)]
        with self.assertRaises(httpx.HTTPStatusError):
            self.module.remove_resource_relations(self.client, "note:created")
        self.assertEqual(len(self.requests), 1)

    def test_failed_delete_is_reported(self) -> None:
        self.responses = [
            httpx.Response(
                httpx.codes.OK,
                json={
                    "tuples": [
                        {
                            "key": {
                                "user": "user:owner",
                                "relation": "owner",
                                "object": "note:created",
                            }
                        }
                    ]
                },
            ),
            httpx.Response(httpx.codes.FORBIDDEN),
        ]
        with self.assertRaises(httpx.HTTPStatusError) as caught:
            self.module.remove_resource_relations(self.client, "note:created")
        self.assertEqual(caught.exception.response.status_code, httpx.codes.FORBIDDEN)  # noqa: WPS441
        self.assertEqual(len(self.requests), 2)
