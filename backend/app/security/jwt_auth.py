from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from app.api.errors import api_error
from app.core.config import settings


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    claims: dict[str, Any]


_bearer_optional = HTTPBearer(auto_error=False)


def _allowed_algorithms() -> list[str]:
    values = [x.strip() for x in settings.sso_jwt_algorithms.split(",") if x.strip()]
    if not values:
        raise api_error(500, "JWT_CONFIG_ERROR", "SSO_JWT_ALGORITHMS is not configured")
    return values


def _extract_user_id(payload: dict[str, Any]) -> str:
    claim_candidates = [settings.sso_user_id_claim, "user_id", "UserID", "sub", "uid"]
    seen: set[str] = set()
    for claim_name in claim_candidates:
        if not isinstance(claim_name, str) or not claim_name.strip():
            continue
        normalized = claim_name.strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        value = payload.get(normalized)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)

    raise api_error(
        401,
        "TOKEN_CLAIMS_INVALID",
        "Token does not contain user id claim",
        {"checked_claims": list(seen)},
    )


def decode_bearer_token(access_token: str) -> AuthUser:
    try:
        header = jwt.get_unverified_header(access_token)
    except InvalidTokenError as exc:
        raise api_error(401, "TOKEN_INVALID", "Malformed token header", {"reason": str(exc)})

    algorithm = header.get("alg")
    if not isinstance(algorithm, str) or not algorithm:
        raise api_error(401, "TOKEN_CLAIMS_INVALID", "Token header does not contain 'alg'")
    allowed_algorithms = _allowed_algorithms()
    if algorithm not in allowed_algorithms:
        raise api_error(401, "TOKEN_INVALID", f"Unsupported token algorithm: {algorithm}")
    if not settings.sso_jwt_secret.strip():
        raise api_error(500, "JWT_CONFIG_ERROR", "SSO_JWT_SECRET is not configured")

    decode_kwargs: dict[str, Any] = {
        "algorithms": [algorithm],
        "options": {"require": ["exp"]},
    }
    if settings.sso_issuer.strip():
        decode_kwargs["issuer"] = settings.sso_issuer
    if settings.sso_audience.strip():
        decode_kwargs["audience"] = settings.sso_audience
    else:
        decode_kwargs["options"]["verify_aud"] = False

    try:
        payload = jwt.decode(access_token, key=settings.sso_jwt_secret, **decode_kwargs)
    except InvalidTokenError as exc:
        raise api_error(401, "TOKEN_INVALID", "Token verification failed", {"reason": str(exc)})

    user_id = _extract_user_id(payload)
    return AuthUser(user_id=user_id, claims=payload)


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
) -> AuthUser | None:
    if credentials is None:
        return None
    if credentials.scheme.lower() != "bearer":
        raise api_error(401, "TOKEN_INVALID", "Authorization scheme must be Bearer")
    return decode_bearer_token(credentials.credentials)


def get_current_user(
    user: AuthUser | None = Depends(get_optional_user),
) -> AuthUser:
    if user is None:
        raise api_error(401, "TOKEN_MISSING", "Authorization token is required")
    return user
