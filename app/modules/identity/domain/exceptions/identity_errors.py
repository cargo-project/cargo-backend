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
