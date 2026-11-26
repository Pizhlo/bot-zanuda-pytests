"""Разбор локального сообщения публичного аудита."""

import unittest

import pytest

from assertions.decision_log import completed_context


class DecisionLogTest(unittest.TestCase):
    """Проверяет обработку неоднозначного текстового контекста."""

    def test_ambiguous_completed_context(self) -> None:
        """Проверяет, что разбор журнала аудита завершается ошибкой, если пробел делает границу значения неоднозначной.

        Диагностическое сообщение объясняет причину ошибки, сохраняя содержимое закрытого поля в тайне.
        """
        event = dict(
            service_name="auth-service",
            operation="check_decision",
            status="completed",
            kind="domain",
            level="info",
            context="map[stage:completed detail:private value]",
        )
        self.assertRaisesRegex(
            pytest.fail.Exception,
            "^Неоднозначное значение с пробелом в текстовом контексте аудита$",
            completed_context,
            event,
        )
