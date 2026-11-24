from __future__ import annotations

from app.composition import trips_factory
from app.composition.resources import AppResources
from app.composition.scope import Scope
from app.infrastructure.health.integration_probes import (
    DatabaseProbe,
    TcpProbe,
    TelegramProbe,
)
from app.infrastructure.telegram.telegram_notification_adapter import TelegramNotificationAdapter
from app.modules.configuration.application.ports import IntegrationProbe
from app.modules.configuration.application.settings_use_cases import (
    CheckIntegrationHealthUseCase,
    GetSettingsUseCase,
    UpdateSettingsUseCase,
)
from app.modules.configuration.infrastructure.settings_persistence import (
    PostgresSystemSettingsRepository,
    TripsMonitoringDefaultsGateway,
)


def _defaults_gateway(scope: Scope) -> TripsMonitoringDefaultsGateway:
    return TripsMonitoringDefaultsGateway(
        trips_factory.get_monitoring_defaults(scope), trips_factory.update_monitoring_defaults(scope)
    )


def get_settings(scope: Scope) -> GetSettingsUseCase:
    return GetSettingsUseCase(PostgresSystemSettingsRepository(scope.session), _defaults_gateway(scope))


def update_settings(scope: Scope) -> UpdateSettingsUseCase:
    return UpdateSettingsUseCase(
        PostgresSystemSettingsRepository(scope.session), _defaults_gateway(scope), scope.uow, scope.audit
    )


def integration_probes(resources: AppResources) -> list[IntegrationProbe]:
    settings = resources.settings
    probes: list[IntegrationProbe] = [
        DatabaseProbe(resources.session_factory),
        TcpProbe("mqtt_iot", "Broker MQTT IoT", settings.mqtt_iot_host, settings.mqtt_iot_port),
        TcpProbe("mqtt_internal", "Broker MQTT interno", settings.mqtt_internal_host, settings.mqtt_internal_port),
        TcpProbe("cep", "Siddhi CEP", settings.siddhi_host, settings.siddhi_port),
    ]
    if isinstance(resources.notification_gateway, TelegramNotificationAdapter):
        probes.append(TelegramProbe(resources.notification_gateway))
    return probes


def check_integration_health(resources: AppResources) -> CheckIntegrationHealthUseCase:
    return CheckIntegrationHealthUseCase(integration_probes(resources))
