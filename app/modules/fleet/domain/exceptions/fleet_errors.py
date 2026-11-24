from __future__ import annotations

from app.shared.domain.errors import BusinessRuleViolationError, ConflictError, EntityNotFoundError


class VehicleNotFoundError(EntityNotFoundError):
    code = "vehicle_not_found"


class DriverNotFoundError(EntityNotFoundError):
    code = "driver_not_found"


class IoTDeviceNotFoundError(EntityNotFoundError):
    code = "device_not_found"


class DuplicateFleetResourceError(ConflictError):
    code = "duplicate_fleet_resource"


class VehicleNotAvailableError(ConflictError):
    code = "vehicle_not_available"


class DriverNotAvailableError(ConflictError):
    code = "driver_not_available"


class DeviceNotAssignableError(ConflictError):
    code = "device_not_assignable"


class VehicleWithoutDeviceError(BusinessRuleViolationError):
    code = "vehicle_without_device"


class InvalidFleetStatusChangeError(BusinessRuleViolationError):
    code = "invalid_fleet_status_change"


class InvalidFleetDataError(BusinessRuleViolationError):
    code = "invalid_fleet_data"


class FleetResourceInUseError(ConflictError):
    """El registro ya tiene historial (viajes o telemetría): borrarlo rompería ese historial."""

    code = "fleet_resource_in_use"
