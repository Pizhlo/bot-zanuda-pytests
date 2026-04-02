"""Логирование ответов сервера с 500-м статусом."""

import logging

import httpx


def log_internal_server_error(
    response: httpx.Response,
    logger: logging.Logger,
    response_error_field: str,
) -> None:
    """Пишет warning, если ответ сервера — 500."""
    if response.status_code == httpx.codes.INTERNAL_SERVER_ERROR:
        try:
            response_data = response.json()
        except ValueError:
            logger.warning("internal server error: %s", response.text)
            return

        if not isinstance(response_data, dict):
            logger.warning("internal server error: %s", response.text)
            return

        logger.warning(
            "internal server error: %s",
            response_data.get(response_error_field, response.text),
        )
