from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from app.composition import configuration_factory
from app.core.http.dependencies import ResourcesDep, ScopeDep
from app.core.http.envelope import ERROR_RESPONSES, CamelModel, DataEnvelope, wrap
from app.modules.configuration.application.settings_use_cases import GeneralSettingsData, SettingsView
from app.modules.identity.presentation.api.auth_dependencies import AdminUser, CurrentUser
from app.modules.trips.presentation.schemas.trip_schemas import MonitoringConfigSchema

settings_router = APIRouter(tags=["settings"], responses=ERROR_RESPONSES)


class GeneralSettingsSchema(CamelModel):
    organization_name: str
    timezone: str
    distance_unit: Literal["km", "mi"]
    default_language: Literal["es", "en"]
    telegram_enabled: bool


class SettingsSchema(CamelModel):
    """Igual a ApiSettings del frontend."""

    general: GeneralSettingsSchema
    monitoring: MonitoringConfigSchema

    @classmethod
    def from_view(cls, view: SettingsView) -> SettingsSchema:
        general = view.general
        return cls(
            general=GeneralSettingsSchema(
                organization_name=general.organization_name,
                timezone=general.timezone,
                distance_unit=general.distance_unit.value,
                default_language=general.default_language.value,
                telegram_enabled=general.telegram_enabled,
            ),
            monitoring=MonitoringConfigSchema(**view.monitoring),
        )


class IntegrationHealthSchema(CamelModel):
    key: str
    name: str
    status: Literal["online", "offline", "unconfigured"]
    detail: str


@settings_router.get("/settings", summary="Global settings and default monitoring thresholds")
async def get_settings(_: CurrentUser, scope: ScopeDep) -> DataEnvelope[SettingsSchema]:
    return wrap(SettingsSchema.from_view(await configuration_factory.get_settings(scope).execute()))


@settings_router.put("/settings", summary="Update settings (ADMIN)")
async def update_settings(body: SettingsSchema, admin: AdminUser, scope: ScopeDep) -> DataEnvelope[SettingsSchema]:
    general = body.general
    view = await configuration_factory.update_settings(scope).execute(
        GeneralSettingsData(
            organization_name=general.organization_name,
            timezone=general.timezone,
            distance_unit=general.distance_unit,
            default_language=general.default_language,
            telegram_enabled=general.telegram_enabled,
        ),
        body.monitoring.to_values(),
        actor_id=admin.id,
    )
    return wrap(SettingsSchema.from_view(view))


@settings_router.get("/integration-health", summary="Live status of external integrations (ADMIN)")
async def integration_health(_: AdminUser, resources: ResourcesDep) -> DataEnvelope[list[IntegrationHealthSchema]]:
    statuses = await configuration_factory.check_integration_health(resources).execute()
    return wrap([IntegrationHealthSchema(key=s.key, name=s.name, status=s.status, detail=s.detail) for s in statuses])
