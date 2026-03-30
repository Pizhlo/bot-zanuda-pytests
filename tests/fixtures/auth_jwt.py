"""Утилиты для сборки и проверки JWT в тестах auth-сервиса."""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any

import jwt

_JWT_HEADER_JSON = b'{"alg":"HS256","typ":"JWT"}'
_DEFAULT_IAT_TOLERANCE_SEC = 5.0


def _base64url(raw: bytes) -> str:
    """Кодирует байты в base64url без паддинга."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _jwt_hs256(payload: dict[str, Any], secret: str) -> str:
    """Собирает и подписывает JWT токен с алгоритмом HS256."""
    header_part = _base64url(_JWT_HEADER_JSON)
    payload_json = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    payload_part = _base64url(payload_json)

    signing_input = f"{header_part}.{payload_part}".encode()
    signature_part = _base64url(
        hmac.new(secret.encode(), signing_input, hashlib.sha256).digest(),
    )
    return f"{header_part}.{payload_part}.{signature_part}"


def make_jwt_token(
    *,
    secret_key: str,
    user_id: str | None = None,
    exp: int | datetime | None = None,
) -> str:
    """
    Генерирует JWT токен для сервиса авторизации.

    Поля добавляются в payload только если переданы:
    - user_id — идентификатор пользователя;
    - exp — unix-время истечения (int) или datetime.
    """
    payload: dict[str, object] = {}

    if user_id is not None:
        payload["user_id"] = user_id

    if exp is not None:
        if isinstance(exp, datetime):
            exp_dt = exp
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            payload["exp"] = int(exp_dt.timestamp())
        else:
            payload["exp"] = exp

    return _jwt_hs256(payload=payload, secret=secret_key)


def assert_iat_recent(
    payload: dict[str, Any],
    *,
    tolerance_sec: float = _DEFAULT_IAT_TOLERANCE_SEC,
) -> None:
    """Проверяет, что iat не слишком давно относительно текущего времени."""
    now = time.time()
    iat = payload.get("iat")
    
    assert iat is not None, "payload does not contain 'iat' field"
    assert abs(now - iat) <= tolerance_sec, f"iat={iat} too far from now={now}"


def check_token_fields(token: str, expected_fields: dict[str, Any]) -> None:
    """Проверяет поля payload JWT и срок жизни по expires_in."""
    payload = jwt.decode(token, options={"verify_signature": False})

    expected_expires_in = expected_fields.get("expires_in")

    for field_name, expected_value in expected_fields.items():
        if field_name == "expires_in":
            continue
        assert payload[field_name] == expected_value

    if expected_expires_in is not None:
        assert payload["exp"] - payload["iat"] == expected_expires_in

    if "iat" in payload:
       assert_iat_recent(payload, tolerance_sec=_DEFAULT_IAT_TOLERANCE_SEC)
