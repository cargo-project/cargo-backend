from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.modules.identity.application.auth_errors import InvalidSessionError
from app.modules.identity.application.ports.token_provider import AccessTokenClaims, IssuedToken


class JwtTokenProvider:
    """Access tokens firmados de vida corta + refresh tokens aleatorios opacos (en BD solo el hash)."""

    def __init__(self, *, secret: str, algorithm: str, issuer: str, access_ttl: timedelta) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._issuer = issuer
        self._access_ttl = access_ttl

    def issue_access_token(self, *, user_id: uuid.UUID, role: str, now: datetime) -> IssuedToken:
        expires_at = now + self._access_ttl
        token = jwt.encode(
            {
                "sub": str(user_id),
                "role": role,
                "typ": "access",
                "iss": self._issuer,
                "iat": int(now.timestamp()),
                "exp": int(expires_at.timestamp()),
                "jti": uuid.uuid4().hex,
            },
            self._secret,
            algorithm=self._algorithm,
        )
        return IssuedToken(value=token, expires_at=expires_at)

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                options={"require": ["sub", "exp", "iat", "typ"]},
            )
            if claims.get("typ") != "access":
                raise InvalidSessionError()
            return AccessTokenClaims(
                user_id=uuid.UUID(str(claims["sub"])),
                role=str(claims.get("role", "")),
                expires_at=datetime.fromtimestamp(int(claims["exp"]), UTC),
            )
        except (jwt.PyJWTError, ValueError) as error:
            raise InvalidSessionError() from error

    def new_refresh_token(self) -> str:
        return secrets.token_urlsafe(48)

    def hash_refresh_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
