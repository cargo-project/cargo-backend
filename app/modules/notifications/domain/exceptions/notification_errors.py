from __future__ import annotations

from app.shared.domain.errors import BusinessRuleViolationError, ConflictError, EntityNotFoundError


class RecipientNotFoundError(EntityNotFoundError):
    code = "recipient_not_found"


class InvalidRecipientError(BusinessRuleViolationError):
    code = "invalid_recipient"


class DuplicateRecipientError(ConflictError):
    code = "duplicate_recipient"


class InvalidNotificationTransitionError(ConflictError):
    code = "invalid_notification_transition"


class NotificationDeliveryError(Exception):
    """La lanza un NotificationGateway. retryable le dice al despachador si vale la pena reintentar."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable
