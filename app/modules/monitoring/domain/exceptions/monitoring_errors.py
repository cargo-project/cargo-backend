from __future__ import annotations

from enum import StrEnum

from app.shared.domain.errors import BusinessRuleViolationError, ConflictError, EntityNotFoundError


class TelemetryRejectionReason(StrEnum):
    TOPIC_DEVICE_MISMATCH = "topic_device_mismatch"
    UNKNOWN_DEVICE = "unknown_device"
    DEVICE_INACTIVE = "device_inactive"
    UNKNOWN_TRIP = "unknown_trip"
    DEVICE_TRIP_MISMATCH = "device_trip_mismatch"
    TRIP_NOT_STARTED = "trip_not_started"
    FUTURE_TIMESTAMP = "future_timestamp"
    BEFORE_TRIP_START = "before_trip_start"
    AFTER_TRIP_END = "after_trip_end"
    SEQUENCE_CONFLICT = "sequence_conflict"
    INVALID_PAYLOAD = "invalid_payload"


class TelemetryRejectedError(BusinessRuleViolationError):
    code = "telemetry_rejected"

    def __init__(self, reason: TelemetryRejectionReason, message: str) -> None:
        super().__init__(message, details={"reason": reason.value})
        self.reason = reason


class MonitoringEventNotFoundError(EntityNotFoundError):
    code = "monitoring_event_not_found"


class UnknownTripError(EntityNotFoundError):
    code = "trip_not_found"


class MonitoringEventAlreadyReviewedError(ConflictError):
    code = "monitoring_event_already_reviewed"


class InvalidDetectedEventError(BusinessRuleViolationError):
    code = "invalid_detected_event"
