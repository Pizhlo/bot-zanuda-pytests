import logging
import uuid
from dataclasses import asdict, replace
from typing import Callable, ContextManager, Generator, Optional

import httpx
import pytest

import src.models.resource as resource
from parameters.auth_service.resource import (  # noqa: WPS235 — типы и таблицы одного набора
    RESOURCE_CREATE_NOTE_CASES,
    CREATE_REMINDER_CASES,
    CREATE_SPACE_CASES,
    DEFAULT_UPDATE_RESOURCE_REQUEST,
    UPDATE_RESOURCE_INVALID_TOKEN_CASES,
    UPDATE_RESOURCE_VALIDATION_ERRORS_CASES,
    InvalidUpdateResourceTokenCase,
    UpdateResourceCase,
    ValidationErrorCase,
)
from src.api_clients.auth_service import AuthServiceV0APIClient
from src.common import audit, errors, fields, ids, server_error_logging
from tests.fixtures import auth_jwt, openfga as openfga_helpers
from assertions.auth_service import assert_audit_payload

logger = logging.getLogger(__name__)


@pytest.fixture()
def isolated_case(
    unregistered_telegram: str,
    case: UpdateResourceCase,
    login: str,
    auth_service_v0_api_client: AuthServiceV0APIClient,
    openfga: httpx.Client,
) -> Generator[UpdateResourceCase, None, None]:
    """Готовит ресурс текущего сценария и подставляет проверенный Telegram ID для запроса.

    Базовая SQL-фикстура не очищает связи ресурсов в OpenFGA. Поэтому
    после сценария удаляем свои связи напрямую в OpenFGA: delete в API сервиса
    пока не реализован. Базовые данные и модель сервиса остаются нетронутыми.
    Сценарий 409 сам создаёт ресурс заранее: он работает отдельно от сценария 200
    и не зависит от порядка pytest. Чужие ресурсы и SQL-данные не затрагиваются.
    Новый UUID также не конфликтует с остатками аварийно прерванного pytest.
    Подготовка 409 входит в try: даже при ошибке запроса/статуса до yield
    finally пытается убрать уже записанные связи, а setup остаётся неуспешным.
    """
    if case.expected_status_code not in (httpx.codes.OK, httpx.codes.CONFLICT):
        yield replace(case, x_telegram_user_id=case.x_telegram_user_id or unregistered_telegram)
        return
    client = auth_service_v0_api_client
    # Подготовка и yield требуют одного finally: раздельные блоки оставят окно без очистки.
    try:  # noqa: WPS229
        if case.expected_status_code == httpx.codes.CONFLICT:
            preparation = replace(case.request, request_id=str(uuid.uuid4()))
            response = client.update_resource(
                asdict(preparation),
                token=login,
                x_telegram_user_id=case.x_telegram_user_id,
            )
            assert response.status_code == httpx.codes.OK, response.text
        yield case
    finally:
        openfga_helpers.remove_resource_relations(
            openfga,
            resource.format_ref(case.request.resource.type, case.request.resource.id),
        )


class TestUpdateResource:
    """
    Тесты для проверки обновления ресурса.
    Обновление ресурса — это сообщение о том, что ресурс добавлен / удалён / изменён.
    Примеры запросов: заметка создана, добавлен участник пространства, изменена роль пользователя в пространстве.
    """

    @pytest.mark.parametrize(
        ("case", "expected_audit_message"),  # noqa: WPS226
        RESOURCE_CREATE_NOTE_CASES,
    )
    def test_create_note(
        self,
        isolated_case: UpdateResourceCase,
        login: str,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """Проверяет ответ синхронизации при создании заметки и причины возможного отказа.

        При успехе ответ описывает заметку и её связи. Для существующей заметки ожидается 409 Conflict,
        для неизвестного пользователя — 404 Not Found. Содержимое очереди ошибок соответствует исходу запроса.
        """
        token = login

        response = auth_service_v0_api_client.update_resource(
            asdict(isolated_case.request),
            token=token,
            x_telegram_user_id=isolated_case.x_telegram_user_id,
        )
        server_error_logging.log_internal_server_error(response, logger, fields.ERROR_FIELD)

        assert response.status_code == isolated_case.expected_status_code, response.text

        if isolated_case.expected_message is not None:
            assert response.json()[fields.ERROR_FIELD] == isolated_case.expected_message

        if isolated_case.expected_response is not None:
            resource.assert_api_response(response.json(), isolated_case.expected_response)

        with auth_service_error_messages_from_rabbitmq as message:
            assert_audit_payload(message, expected_audit_message, errors.NO_AUDIT_MESSAGES_ERROR)

    @pytest.mark.parametrize(
        ("case", "expected_audit_message"),
        CREATE_SPACE_CASES,
    )
    def test_create_space(
        self,
        isolated_case: UpdateResourceCase,
        login: str,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """Проверяет ответ синхронизации при создании пространства и причины возможного отказа.

        При успехе ответ описывает пространство и его связи. Для существующего пространства ожидается 409 Conflict,
        для неизвестного пользователя — 404 Not Found. Содержимое очереди ошибок соответствует исходу запроса.
        """
        token = login

        response = auth_service_v0_api_client.update_resource(
            asdict(isolated_case.request),
            token=token,
            x_telegram_user_id=isolated_case.x_telegram_user_id,
        )
        server_error_logging.log_internal_server_error(response, logger, fields.ERROR_FIELD)

        assert response.status_code == isolated_case.expected_status_code, response.text

        if isolated_case.expected_message is not None:
            assert response.json()[fields.ERROR_FIELD] == isolated_case.expected_message

        if isolated_case.expected_response is not None:
            resource.assert_api_response(response.json(), isolated_case.expected_response)

        with auth_service_error_messages_from_rabbitmq as message:
            assert_audit_payload(message, expected_audit_message, errors.NO_AUDIT_MESSAGES_ERROR)

    @pytest.mark.parametrize(
        ("case", "expected_audit_message"),
        CREATE_REMINDER_CASES,
    )
    def test_create_reminder(
        self,
        isolated_case: UpdateResourceCase,
        login: str,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """Проверяет ответ синхронизации при создании напоминания и причины возможного отказа.

        При успехе ответ описывает напоминание и его связи. Для существующего напоминания ожидается 409 Conflict,
        для неизвестного пользователя — 404 Not Found. Содержимое очереди ошибок соответствует исходу запроса.
        """
        token = login

        response = auth_service_v0_api_client.update_resource(
            asdict(isolated_case.request),
            token=token,
            x_telegram_user_id=isolated_case.x_telegram_user_id,
        )
        server_error_logging.log_internal_server_error(response, logger, fields.ERROR_FIELD)

        assert response.status_code == isolated_case.expected_status_code, response.text

        if isolated_case.expected_message is not None:
            assert response.json()[fields.ERROR_FIELD] == isolated_case.expected_message

        if isolated_case.expected_response is not None:
            resource.assert_api_response(response.json(), isolated_case.expected_response)

        with auth_service_error_messages_from_rabbitmq as message:
            assert_audit_payload(message, expected_audit_message, errors.NO_AUDIT_MESSAGES_ERROR)

    @pytest.mark.parametrize(
        ("invalid_case", "expected_audit_message"),
        UPDATE_RESOURCE_INVALID_TOKEN_CASES,
    )
    def test_update_resource_invalid_token(
        self,
        invalid_case: InvalidUpdateResourceTokenCase,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        jwt_token_factory: Callable[..., str],
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """Проверяет отказ в синхронизации при недействительном токене или неверном заголовке пользователя.

        Сервис возвращает 401 Unauthorized при ошибке аутентификации. При действительном JWT и Telegram ID
        с ведущим нулём ожидается 400 Bad Request. Событие аудита указывает причину первого сбоя.
        """
        token = auth_jwt.optional_token(jwt_token_factory, invalid_case.token_fields)

        response = auth_service_v0_api_client.update_resource(
            asdict(DEFAULT_UPDATE_RESOURCE_REQUEST),
            token=token,
            x_telegram_user_id=invalid_case.telegram_user_id,
        )
        server_error_logging.log_internal_server_error(response, logger, fields.ERROR_FIELD)

        assert response.status_code == invalid_case.expected_status_code, response.text

        if invalid_case.expected_message is not None:
            assert invalid_case.expected_message == response.json()[fields.ERROR_FIELD]

        if invalid_case.expected_response is not None:
            resource.assert_api_response(
                response.json(), invalid_case.expected_response
            )

        with auth_service_error_messages_from_rabbitmq as message:
            assert_audit_payload(message, expected_audit_message, errors.NO_AUDIT_MESSAGES_ERROR)

    @pytest.mark.parametrize(
        "case",
        UPDATE_RESOURCE_VALIDATION_ERRORS_CASES,
    )
    def test_update_resource_validation_errors(
        self,
        case: ValidationErrorCase,
        login: str,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """Проверяет валидацию запроса синхронизации после успешной аутентификации.

        Недопустимые связи, несовместимые операция и событие или неверно указанное изменение приводят
        к 400 Bad Request. Ответ и аудит сообщают причину отказа, а событие также указывает этап проверки.
        """
        response = auth_service_v0_api_client.update_resource(
            asdict(case.request),
            token=login,
            x_telegram_user_id=ids.ADMIN_USER_ID,
        )
        server_error_logging.log_internal_server_error(response, logger, fields.ERROR_FIELD)

        # validateRequest в fga.UpdateResource: level=debug,
        # error_code=WRITE_FAILED_DUE_TO_INVALID_INPUT, cause=Err.Error()
        # (совпадает с error.message в HTTP-ответе).
        validation_audit_message = audit.AuditMessage(
            service_name=audit.AUTH_SERVICE_NAME,
            level=audit.Level.DEBUG,
            cause=case.expected_response.error.message,
            message="Invalid resource update request",
            error_code=audit.ErrorCode.WRITE_FAILED_DUE_TO_INVALID_INPUT,
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.FGA_UPDATE_RESOURCE,
            status=audit.Status.FAILED,
            context={
                fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT,
                fields.USER_ID_FIELD: ids.ADMIN_USER_ID_UUID,
                audit.STAGE_FIELD: "validate_resource",
            },
        )

        with auth_service_error_messages_from_rabbitmq as message:
            assert_audit_payload(message, validation_audit_message, errors.NO_AUDIT_MESSAGES_ERROR)

        assert response.status_code == case.expected_status_code, response.text
        resource.assert_api_response(response.json(), case.expected_response)
