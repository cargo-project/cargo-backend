from __future__ import annotations

from app.shared.application.errors import AuthenticationError


class InvalidCredentialsError(AuthenticationError):
    """Genérico a propósito: no revela si la cuenta existe, está bloqueada o inactiva."""

    code = "invalid_credentials"

    def __init__(self) -> None:
        super().__init__("Credenciales inválidas o cuenta bloqueada temporalmente.")


class InvalidSessionError(AuthenticationError):
    code = "invalid_session"

    def __init__(self) -> None:
        super().__init__("La sesión no es válida o ha expirado.")
