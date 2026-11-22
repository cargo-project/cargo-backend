from __future__ import annotations

from app.shared.domain.errors import BusinessRuleViolationError, ConflictError, EntityNotFoundError


class TripNotFoundError(EntityNotFoundError):
    code = "trip_not_found"


class ClientNotFoundError(EntityNotFoundError):
    code = "client_not_found"


class InvalidTripError(BusinessRuleViolationError):
    """Los datos del viaje rompen una regla de planificación (mismo origen y destino, sin destinatarios...)."""

    code = "invalid_trip"


class InvalidTripStateError(ConflictError):
    """La transición pedida no se permite desde el estado actual."""

    code = "invalid_trip_state"


class TripAlreadyStartedError(InvalidTripStateError):
    code = "trip_already_started"


class TripAlreadyFinishedError(InvalidTripStateError):
    code = "trip_already_finished"


class TripNotStartedError(InvalidTripStateError):
    code = "trip_not_started"


class InvalidMonitoringConfigurationError(BusinessRuleViolationError):
    code = "invalid_monitoring_configuration"


class InvalidGeofenceError(BusinessRuleViolationError):
    code = "invalid_geofence"
