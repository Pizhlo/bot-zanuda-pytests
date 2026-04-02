"""Утилиты для сборки и проверки JWT в тестах auth-сервиса."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from dataclasses import dataclass

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

@dataclass(frozen=True)
class TokenFields:
    """Параметры, из которых собирается payload токена."""
    sub: str | None = None # кто получил токен (bot)
    aud: list[str] | None = None # audience
    iss: str | None = None # issuer
    iat: int | None = None # issued at
    exp: int | None = None # expires at
    scope: str | None = None # scope

_sub_field = "sub"
_aud_field = "aud"
_iss_field = "iss"
_iat_field = "iat"
_exp_field = "exp"
_scope_field = "scope"

def make_jwt_token(
    *,
    secret_key: str,
    token_fields: TokenFields,
) -> str:
    """
    Генерирует JWT токен для сервиса авторизации.

    Поля добавляются в payload только если переданы:
    - user_id — идентификатор пользователя;
    - exp — unix-время истечения (int) или datetime.
    """
    payload: dict[str, object] = {}

    if token_fields.sub is not None:
        payload[_sub_field] = token_fields.sub

    if token_fields.exp is not None:
        payload[_exp_field] = token_fields.exp

    if token_fields.aud is not None:
        payload[_aud_field] = token_fields.aud

    if token_fields.iss is not None:
        payload[_iss_field] = token_fields.iss

    if token_fields.iat is not None:
        payload[_iat_field] = token_fields.iat

    if token_fields.scope is not None:
        payload[_scope_field] = token_fields.scope

    return _jwt_hs256(payload=payload, secret=secret_key)


def assert_iat_recent(
    payload: dict[str, Any],
    *,
    tolerance_sec: float = _DEFAULT_IAT_TOLERANCE_SEC,
) -> None:
    """Проверяет, что iat не слишком давно относительно текущего времени."""
    now = time.time()
    iat = payload.get(_iat_field)
    
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
        assert payload[_exp_field] - payload[_iat_field] == expected_expires_in

    if _iat_field in payload:
       assert_iat_recent(payload, tolerance_sec=_DEFAULT_IAT_TOLERANCE_SEC)
