from __future__ import annotations

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class Argon2PasswordHasher:
    """Argon2id (RFC 9106) con los valores por defecto de argon2-cffi, lo que recomienda OWASP."""

    def __init__(self) -> None:
        self._hasher = _Argon2()
        self._dummy_hash = self._hasher.hash("cargo-timing-equaliser")

    def verify_against_dummy(self, password: str) -> None:
        self.verify(self._dummy_hash, password)

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)
