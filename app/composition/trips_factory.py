from __future__ import annotations

from app.composition.scope import Scope
from app.modules.fleet.infrastructure.persistence.postgres_fleet_repositories import (
    PostgresDriverAssignmentRepository,
    PostgresDriverRepository,
    PostgresIoTDeviceRepository,
    PostgresVehicleRepository,
)
from app.modules.trips.application.use_cases.client_use_cases import (
    CreateClientUseCase,
    ListClientsUseCase,
)
from app.modules.trips.application.use_cases.create_trip import CreateTripUseCase
from app.modules.trips.application.use_cases.geocoding_use_cases import (
    ReverseGeocodeUseCase,
    SearchLocationsUseCase,
)
from app.modules.trips.application.use_cases.geofence_use_cases import (
    CreateGeofenceUseCase,
    ListGeofencesUseCase,
)
from app.modules.trips.application.use_cases.monitoring_defaults_use_cases import (
    GetMonitoringDefaultsUseCase,
    UpdateMonitoringDefaultsUseCase,
)
from app.modules.trips.application.use_cases.trip_lifecycle import (
    CancelTripUseCase,
    FinishTripUseCase,
    ReannounceActiveTripsUseCase,
    StartTripUseCase,
    UpdateMonitoringConfigurationUseCase,
)
from app.modules.trips.application.use_cases.trip_queries import (
    GetTripUseCase,
    ListTripsUseCase,
)
from app.modules.trips.infrastructure.adapters.fleet_allocation_adapter import FleetAllocationAdapter
from app.modules.trips.infrastructure.adapters.sql_recipient_directory import SqlRecipientDirectory
from app.modules.trips.infrastructure.persistence.postgres_trip_repository import PostgresTripRepository
from app.modules.trips.infrastructure.persistence.postgres_trip_support_repositories import (
    PostgresClientRepository,
    PostgresGeofenceRepository,
    PostgresMonitoringDefaultsRepository,
)
from app.modules.trips.infrastructure.persistence.sql_trip_read_model import SqlTripReadModel


def _fleet_allocation(scope: Scope) -> FleetAllocationAdapter:
    session = scope.session
    return FleetAllocationAdapter(
        PostgresVehicleRepository(session),
        PostgresDriverRepository(session),
        PostgresIoTDeviceRepository(session),
        PostgresDriverAssignmentRepository(session),
    )


def create_trip(scope: Scope) -> CreateTripUseCase:
    session = scope.session
    return CreateTripUseCase(
        trips=PostgresTripRepository(session),
        clients=PostgresClientRepository(session),
        defaults=PostgresMonitoringDefaultsRepository(session),
        fleet=_fleet_allocation(scope),
        recipients=SqlRecipientDirectory(session),
        uow=scope.uow,
        clock=scope.resources.clock,
        audit=scope.audit,
    )


def start_trip(scope: Scope) -> StartTripUseCase:
    return StartTripUseCase(
        PostgresTripRepository(scope.session),
        _fleet_allocation(scope),
        scope.publisher,
        scope.uow,
        scope.resources.clock,
        scope.audit,
    )


def finish_trip(scope: Scope) -> FinishTripUseCase:
    return FinishTripUseCase(
        PostgresTripRepository(scope.session),
        _fleet_allocation(scope),
        scope.publisher,
        scope.uow,
        scope.resources.clock,
        scope.audit,
    )


def cancel_trip(scope: Scope) -> CancelTripUseCase:
    return CancelTripUseCase(
        PostgresTripRepository(scope.session),
        _fleet_allocation(scope),
        scope.publisher,
        scope.uow,
        scope.resources.clock,
        scope.audit,
    )


def update_monitoring_configuration(scope: Scope) -> UpdateMonitoringConfigurationUseCase:
    return UpdateMonitoringConfigurationUseCase(
        PostgresTripRepository(scope.session),
        scope.publisher,
        scope.uow,
        scope.resources.clock,
        scope.audit,
    )


def reannounce_active_trips(scope: Scope) -> ReannounceActiveTripsUseCase:
    return ReannounceActiveTripsUseCase(
        PostgresTripRepository(scope.session), scope.publisher, scope.uow, scope.resources.clock
    )


def list_trips(scope: Scope) -> ListTripsUseCase:
    return ListTripsUseCase(SqlTripReadModel(scope.session))


def get_trip(scope: Scope) -> GetTripUseCase:
    return GetTripUseCase(SqlTripReadModel(scope.session))


def list_clients(scope: Scope) -> ListClientsUseCase:
    return ListClientsUseCase(PostgresClientRepository(scope.session))


def create_client(scope: Scope) -> CreateClientUseCase:
    return CreateClientUseCase(PostgresClientRepository(scope.session), scope.uow, scope.resources.clock, scope.audit)


def list_geofences(scope: Scope) -> ListGeofencesUseCase:
    return ListGeofencesUseCase(PostgresGeofenceRepository(scope.session))


def create_geofence(scope: Scope) -> CreateGeofenceUseCase:
    return CreateGeofenceUseCase(
        PostgresGeofenceRepository(scope.session), scope.uow, scope.resources.clock, scope.audit
    )


def get_monitoring_defaults(scope: Scope) -> GetMonitoringDefaultsUseCase:
    return GetMonitoringDefaultsUseCase(PostgresMonitoringDefaultsRepository(scope.session))


def update_monitoring_defaults(scope: Scope) -> UpdateMonitoringDefaultsUseCase:
    return UpdateMonitoringDefaultsUseCase(PostgresMonitoringDefaultsRepository(scope.session), scope.audit)


def search_locations(scope: Scope) -> SearchLocationsUseCase:
    return SearchLocationsUseCase(scope.resources.geocoding_provider)


def reverse_geocode(scope: Scope) -> ReverseGeocodeUseCase:
    return ReverseGeocodeUseCase(scope.resources.geocoding_provider)
