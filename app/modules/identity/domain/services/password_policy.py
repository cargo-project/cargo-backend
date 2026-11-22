from __future__ import annotations

from app.modules.identity.domain.exceptions.identity_errors import WeakPasswordError

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


class PasswordPolicy:
    """Política por longitud, alineada con OWASP ASVS 2.1 (sin reglas de composición arbitrarias)."""

    @staticmethod
    def validate(password: str, *, email: str | None = None) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise WeakPasswordError(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")
        if len(password) > MAX_PASSWORD_LENGTH:
            raise WeakPasswordError(f"La contraseña no puede superar {MAX_PASSWORD_LENGTH} caracteres.")
        if email and password.strip().lower() == email.strip().lower():
            raise WeakPasswordError("La contraseña no puede ser igual al correo.")
