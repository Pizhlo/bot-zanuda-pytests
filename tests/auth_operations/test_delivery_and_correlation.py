"""Доставка итогового аудита до и после разрыва соединения с брокером."""

import json
import os


from assertions import audit_delivery
from parameters.auth_service.decision_history import BROKER_READS
from src.models.decision import Actor, Role
from src.models.space import SpaceType
from src.storages.postgres_client import PostgresClient
from tests.fixtures.broker_delivery import check_read, wait_for_disconnect
from tests.fixtures.decisions import DecisionClient
from tests.fixtures.fault_proxy import disconnected
from tests.fixtures.rabbitmq import AuditStream
from tests.fixtures.service_log import ServiceLog


def test_delivery_before_and_after_disconnect(  # noqa: WPS211 — независимые наблюдения HTTP, RabbitMQ и PostgreSQL
    observed_decisions: DecisionClient,
    actors: dict[Role, Actor],
    spaces: dict[str, str],
    audit_stream: AuditStream,
    postgres_client: PostgresClient,
) -> None:
    """Проверяет влияние разрыва связи с RabbitMQ на решения о чтении общего пространства.

    Владелец получает разрешение, а посторонний получает отказ. Пока брокер доступен, оба решения
    доставляются в очередь. После разрыва оба ответа по-прежнему сохраняются в истории, а локальный журнал
    содержит итоговое событие и предупреждение о неудачной доставке для каждой попытки.
    """
    log = ServiceLog.start(os.environ["AUTH_OBSERVED_LOG"])
    shared = spaces[SpaceType.SHARED]
    for case in BROKER_READS:
        decision = check_read(observed_decisions, actors[case.role], shared, case)
        with audit_stream() as raw:
            assert raw is not None
            audit_delivery.assert_completed(json.loads(raw), decision)

    with disconnected("rabbitmq"):
        wait_for_disconnect(observed_decisions, actors[Role.OWNER], shared, log)
        for case in BROKER_READS:
            decision = check_read(observed_decisions, actors[case.role], shared, case)
            audit_delivery.assert_delivery_log(
                log.wait(decision["request_id"], "decision audit delivery failed"),
                decision,
            )
            audit_delivery.assert_saved_delivery(postgres_client, decision)
