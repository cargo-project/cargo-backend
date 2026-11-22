from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class IssuedToken:
    value: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    role: str
    expires_at: datetime


class TokenProvider(Protocol):
    def issue_access_token(self, *, user_id: uuid.UUID, role: str, now: datetime) -> IssuedToken: ...

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        """Lanza InvalidSessionError si el token está mal formado, adulterado o vencido."""
        ...

    def new_refresh_token(self) -> str: ...

    def hash_refresh_token(self, token: str) -> str: ...
