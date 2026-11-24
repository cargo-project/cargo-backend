from __future__ import annotations

from app.shared.application.errors import AuthenticationError, AuthorizationError


class InvalidCredentialsError(AuthenticationError):
    """Genérico a propósito: no revela si la cuenta existe, está bloqueada o inactiva."""

    code = "invalid_credentials"

    def __init__(self) -> None:
        super().__init__("Credenciales inválidas o cuenta bloqueada temporalmente.")


class InvalidSessionError(AuthenticationError):
    code = "invalid_session"

    def __init__(self) -> None:
        super().__init__("La sesión no es válida o ha expirado.")


class AccountPendingApprovalError(AuthorizationError):
    """Solo se informa después de comprobar la contraseña: no revela cuentas a quien no la conoce."""

    code = "account_pending_approval"

    def __init__(self) -> None:
        super().__init__("Tu cuenta todavía no está activa: un administrador debe aprobarla o reactivarla.")
