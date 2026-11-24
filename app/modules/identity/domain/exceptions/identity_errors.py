from __future__ import annotations

from app.shared.domain.errors import BusinessRuleViolationError, ConflictError, EntityNotFoundError


class InvalidEmailError(BusinessRuleViolationError):
    code = "invalid_email"


class WeakPasswordError(BusinessRuleViolationError):
    code = "weak_password"


class EmailAlreadyRegisteredError(ConflictError):
    code = "email_already_registered"


class UserNotFoundError(EntityNotFoundError):
    code = "user_not_found"


class SelfLockoutError(BusinessRuleViolationError):
    """Un administrador no puede quitarse el rol ni desactivar su propia cuenta (evita quedar sin admin)."""

    code = "self_lockout"


class TelegramRequiredError(BusinessRuleViolationError):
    """Toda cuenta necesita un chat de Telegram: ahí llegan los códigos para recuperar la contraseña."""

    code = "telegram_required"


class TelegramUnreachableError(BusinessRuleViolationError):
    """El bot no pudo escribir a ese chat (ID incorrecto o la persona no inició el bot)."""

    code = "telegram_unreachable"


class InvalidResetCodeError(BusinessRuleViolationError):
    code = "invalid_reset_code"
