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
def isolated_resource(
    case: UpdateResourceCase,
    login: str,
    auth_service_v0_api_client: AuthServiceV0APIClient,
    openfga: httpx.Client,
) -> Generator[None, None, None]:
    """Готовит и удаляет только ресурс текущего сценария создания.

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
        yield
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
        yield
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
    @pytest.mark.usefixtures("isolated_resource")
    def test_create_note(
        self,
        case: UpdateResourceCase,
        login: str,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """Тест на создание заметки."""
        token = login

        response = auth_service_v0_api_client.update_resource(
            asdict(case.request),
            token=token,
            x_telegram_user_id=case.x_telegram_user_id,
        )
        server_error_logging.log_internal_server_error(response, logger, fields.ERROR_FIELD)

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        assert response.status_code == case.expected_status_code, response.text

        if case.expected_message is not None:
            assert response.json()[fields.ERROR_FIELD] == case.expected_message

        if case.expected_response is not None:
            resource.assert_api_response(response.json(), case.expected_response)

        assert_audit_payload(
            message, expected_audit_message, errors.NO_AUDIT_MESSAGES_ERROR
        )

    @pytest.mark.parametrize(
        ("case", "expected_audit_message"),
        CREATE_SPACE_CASES,
    )
    @pytest.mark.usefixtures("isolated_resource")
    def test_create_space(
        self,
        case: UpdateResourceCase,
        login: str,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """Тест на создание пространства."""
        token = login

        response = auth_service_v0_api_client.update_resource(
            asdict(case.request),
            token=token,
            x_telegram_user_id=case.x_telegram_user_id,
        )
        server_error_logging.log_internal_server_error(response, logger, fields.ERROR_FIELD)

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        assert response.status_code == case.expected_status_code, response.text

        if case.expected_message is not None:
            assert response.json()[fields.ERROR_FIELD] == case.expected_message

        if case.expected_response is not None:
            resource.assert_api_response(response.json(), case.expected_response)

        assert_audit_payload(
            message, expected_audit_message, errors.NO_AUDIT_MESSAGES_ERROR
        )

    @pytest.mark.parametrize(
        ("case", "expected_audit_message"),
        CREATE_REMINDER_CASES,
    )
    @pytest.mark.usefixtures("isolated_resource")
    def test_create_reminder(
        self,
        case: UpdateResourceCase,
        login: str,
        expected_audit_message: audit.AuditMessage | None,
        auth_service_v0_api_client: AuthServiceV0APIClient,
        auth_service_error_messages_from_rabbitmq: ContextManager[Optional[bytes]],
    ) -> None:
        """Тест на создание напоминания."""
        token = login

        response = auth_service_v0_api_client.update_resource(
            asdict(case.request),
            token=token,
            x_telegram_user_id=case.x_telegram_user_id,
        )
        server_error_logging.log_internal_server_error(response, logger, fields.ERROR_FIELD)

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        assert response.status_code == case.expected_status_code, response.text

        if case.expected_message is not None:
            assert response.json()[fields.ERROR_FIELD] == case.expected_message

        if case.expected_response is not None:
            resource.assert_api_response(response.json(), case.expected_response)

        assert_audit_payload(
            message, expected_audit_message, errors.NO_AUDIT_MESSAGES_ERROR
        )

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
        """Тест на обновление ресурса."""
        token = auth_jwt.optional_token(jwt_token_factory, invalid_case.token_fields)

        response = auth_service_v0_api_client.update_resource(
            asdict(DEFAULT_UPDATE_RESOURCE_REQUEST),
            token=token,
            x_telegram_user_id=invalid_case.telegram_user_id,
        )
        server_error_logging.log_internal_server_error(response, logger, fields.ERROR_FIELD)

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        assert response.status_code == invalid_case.expected_status_code, response.text

        if invalid_case.expected_message is not None:
            assert invalid_case.expected_message == response.json()[fields.ERROR_FIELD]

        if invalid_case.expected_response is not None:
            resource.assert_api_response(
                response.json(), invalid_case.expected_response
            )

        assert_audit_payload(
            message, expected_audit_message, errors.NO_AUDIT_MESSAGES_ERROR
        )

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
        """Тест на валидацию запросов update_resource при создании ресурсов."""
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
            error_code=audit.ErrorCode.WRITE_FAILED_DUE_TO_INVALID_INPUT,
            kind=audit.Kind.VALIDATION,
            operation=audit.Operation.FGA_UPDATE_RESOURCE,
            status=audit.Status.FAILED,
            context={
                fields.USER_AGENT_FIELD: audit.TEST_USER_AGENT,
                fields.USER_ID_FIELD: ids.ADMIN_USER_ID,
            },
        )

        with auth_service_error_messages_from_rabbitmq as rabbitmq_message:
            message = rabbitmq_message

        assert_audit_payload(
            message, validation_audit_message, errors.NO_AUDIT_MESSAGES_ERROR
        )

        assert response.status_code == case.expected_status_code, response.text
        resource.assert_api_response(response.json(), case.expected_response)
