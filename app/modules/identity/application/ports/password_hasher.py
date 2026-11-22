from __future__ import annotations

from typing import Protocol


class PasswordHasher(Protocol):
    """Hash de contraseñas adaptativo y de un solo sentido (implementado con Argon2id)."""

    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool: ...

    def verify_against_dummy(self, password: str) -> None:
        """Tarda lo mismo que una verificación real (para no delatar qué usuarios existen)."""
        ...
