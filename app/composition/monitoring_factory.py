from __future__ import annotations

from datetime import timedelta

from app.composition.scope import Scope
from app.infrastructure.mqtt.mqtt_edge_assignment_publisher import MqttEdgeAssignmentPublisher
from app.infrastructure.mqtt.mqtt_event_publisher import MqttEventPublisher
from app.modules.monitoring.application.services.telemetry_deduplicator import TelemetryDeduplicator
from app.modules.monitoring.application.use_cases.announce_trip_assignment import AnnounceTripAssignmentUseCase
from app.modules.monitoring.application.use_cases.enrich_telemetry import EnrichTelemetryUseCase
from app.modules.monitoring.application.use_cases.ingest_telemetry import IngestTelemetryUseCase
from app.modules.monitoring.application.use_cases.monitoring_queries import (
    AcknowledgeMonitoringEventUseCase,
    GetDashboardUseCase,
    GetMonitoringEventsUseCase,
    GetTripTelemetryUseCase,
    GetTripTrackUseCase,
)
from app.modules.monitoring.application.use_cases.register_detected_event import (
    RegisterDetectedEventUseCase,
)
from app.modules.monitoring.domain.services.telemetry_acceptance_policy import TelemetryAcceptancePolicy
from app.modules.monitoring.domain.services.temporal_classifier import TemporalClassifier
from app.modules.monitoring.infrastructure.adapters.sql_monitoring_adapters import (
    SqlDeviceConnectionRecorder,
    SqlDeviceDirectory,
    SqlMonitoringTripDirectory,
    SqlTelemetryContextProvider,
)
from app.modules.monitoring.infrastructure.geospatial.postgis_spatial_context_analyzer import (
    PostgisSpatialContextAnalyzer,
)
from app.modules.monitoring.infrastructure.persistence.postgres_monitoring_repositories import (
    PostgresMonitoringEventRepository,
    PostgresTelemetryRepository,
)
from app.modules.monitoring.infrastructure.persistence.sql_monitoring_read_model import (
    SqlMonitoringReadModel,
)


def ingest_telemetry(scope: Scope) -> IngestTelemetryUseCase:
    settings = scope.resources.settings
    telemetry = PostgresTelemetryRepository(scope.session)
    return IngestTelemetryUseCase(
        telemetry=telemetry,
        contexts=SqlTelemetryContextProvider(scope.session),
        connections=SqlDeviceConnectionRecorder(scope.session),
        deduplicator=TelemetryDeduplicator(telemetry),
        policy=TelemetryAcceptancePolicy(max_future_skew=timedelta(seconds=settings.max_future_skew_seconds)),
        classifier=TemporalClassifier(timedelta(seconds=settings.live_tolerance_seconds)),
        publisher=scope.publisher,
        uow=scope.uow,
        clock=scope.resources.clock,
    )


def announce_trip_assignment(scope: Scope, iot_publisher: MqttEventPublisher) -> AnnounceTripAssignmentUseCase:
    return AnnounceTripAssignmentUseCase(SqlDeviceDirectory(scope.session), MqttEdgeAssignmentPublisher(iot_publisher))


def enrich_telemetry(scope: Scope) -> EnrichTelemetryUseCase:
    return EnrichTelemetryUseCase(
        PostgresTelemetryRepository(scope.session),
        PostgisSpatialContextAnalyzer(scope.session),
        scope.publisher,
        scope.uow,
        scope.resources.clock,
    )


def register_detected_event(scope: Scope) -> RegisterDetectedEventUseCase:
    return RegisterDetectedEventUseCase(
        PostgresMonitoringEventRepository(scope.session),
        PostgresTelemetryRepository(scope.session),
        SqlMonitoringTripDirectory(scope.session),
        scope.uow,
        scope.resources.clock,
    )


def get_monitoring_events(scope: Scope) -> GetMonitoringEventsUseCase:
    return GetMonitoringEventsUseCase(SqlMonitoringReadModel(scope.session))


def acknowledge_monitoring_event(scope: Scope) -> AcknowledgeMonitoringEventUseCase:
    return AcknowledgeMonitoringEventUseCase(
        PostgresMonitoringEventRepository(scope.session),
        SqlMonitoringReadModel(scope.session),
        scope.uow,
        scope.resources.clock,
        scope.audit,
    )


def get_trip_track(scope: Scope) -> GetTripTrackUseCase:
    return GetTripTrackUseCase(SqlMonitoringReadModel(scope.session))


def get_trip_telemetry(scope: Scope) -> GetTripTelemetryUseCase:
    return GetTripTelemetryUseCase(SqlMonitoringReadModel(scope.session))


def get_dashboard(scope: Scope) -> GetDashboardUseCase:
    window = timedelta(seconds=scope.resources.settings.device_online_window_seconds)
    return GetDashboardUseCase(SqlMonitoringReadModel(scope.session), scope.resources.clock, window)
