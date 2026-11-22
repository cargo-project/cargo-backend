"""Contratos HTTP de las pantallas de viajes (ApiTrip, ApiMonitoringConfig, formulario de crear viaje)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.http.envelope import CamelModel
from app.modules.trips.application.dto.trip_dto import CreateTripCommand, TripView
from app.modules.trips.domain.entities.client import Client
from app.modules.trips.domain.entities.geofence import Geofence
from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration


class Coordinates(CamelModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class MonitoringConfigSchema(CamelModel):
    """ApiMonitoringConfig. Desviación = alejarse del destino más de routeDeviationMinIncreaseM
    durante routeDeviationMinEvents lecturas y routeDeviationWindowSeconds.
    """

    route_deviation_min_events: int
    route_deviation_min_increase_m: float
    route_deviation_window_seconds: int
    stop_speed_kmh: float
    stop_max_displacement_m: float
    stop_duration_seconds: int
    connection_loss_seconds: int
    arrival_radius_m: float
    arrival_confirmation_seconds: int
    sequence_gap_wait_seconds: int

    @classmethod
    def from_domain(cls, config: MonitoringConfiguration) -> MonitoringConfigSchema:
        return cls(**config.as_dict())

    def to_values(self) -> dict[str, float | int]:
        return self.model_dump(by_alias=False)


class MonitoringConfigPatch(CamelModel):
    route_deviation_min_events: int | None = None
    route_deviation_min_increase_m: float | None = None
    route_deviation_window_seconds: int | None = None
    stop_speed_kmh: float | None = None
    stop_max_displacement_m: float | None = None
    stop_duration_seconds: int | None = None
    connection_loss_seconds: int | None = None
    arrival_radius_m: float | None = None
    arrival_confirmation_seconds: int | None = None
    sequence_gap_wait_seconds: int | None = None

    def changes(self) -> dict[str, float | int]:
        return self.model_dump(by_alias=False, exclude_none=True)


class RecipientSchema(CamelModel):
    id: uuid.UUID
    name: str
    telegram_chat_id: str
    active: bool


class CreateTripRequest(CamelModel):
    vehicle_code: str = Field(min_length=2, max_length=24)
    driver_code: str = Field(min_length=2, max_length=24)
    origin_label: str = Field(min_length=1, max_length=300)
    origin: Coordinates
    destination_label: str = Field(min_length=1, max_length=300)
    destination: Coordinates
    cargo_description: str = Field(min_length=3, max_length=500)
    planned_start_at: datetime | None = None
    recipient_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    client_id: uuid.UUID | None = None

    def to_command(self) -> CreateTripCommand:
        return CreateTripCommand(
            vehicle_code=self.vehicle_code,
            driver_code=self.driver_code,
            origin_label=self.origin_label,
            origin_latitude=self.origin.latitude,
            origin_longitude=self.origin.longitude,
            destination_label=self.destination_label,
            destination_latitude=self.destination.latitude,
            destination_longitude=self.destination.longitude,
            cargo_description=self.cargo_description,
            recipient_ids=frozenset(self.recipient_ids),
            planned_start_at=self.planned_start_at,
            client_id=self.client_id,
        )


class TripResponse(CamelModel):
    id: uuid.UUID
    code: str
    vehicle_code: str
    plate: str
    driver_code: str
    driver_name: str
    origin_label: str
    origin: Coordinates
    destination_label: str
    destination: Coordinates
    cargo_description: str
    status: Literal["configured", "ongoing", "completed", "cancelled"]
    planned_start_at: datetime | None = None
    actual_start_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    progress: int
    recipients: list[RecipientSchema]
    monitoring_config: MonitoringConfigSchema
    client_name: str | None = None
    direct_distance_m: float  # origen -> destino en línea recta (no se planifica ruta)

    @classmethod
    def from_view(cls, view: TripView) -> TripResponse:
        return cls(
            id=view.id,
            code=view.code,
            vehicle_code=view.vehicle_code,
            plate=view.plate,
            driver_code=view.driver_code,
            driver_name=view.driver_name,
            origin_label=view.origin_label,
            origin=Coordinates(latitude=view.origin_latitude, longitude=view.origin_longitude),
            destination_label=view.destination_label,
            destination=Coordinates(latitude=view.destination_latitude, longitude=view.destination_longitude),
            cargo_description=view.cargo_description,
            status=view.status,
            planned_start_at=view.planned_start_at,
            actual_start_at=view.started_at,
            completed_at=view.completed_at,
            cancelled_at=view.cancelled_at,
            progress=view.progress,
            recipients=[
                RecipientSchema(id=r.id, name=r.name, telegram_chat_id=r.telegram_chat_id, active=r.active)
                for r in view.recipients
            ],
            monitoring_config=MonitoringConfigSchema.from_domain(view.monitoring_configuration),
            client_name=view.client_name,
            direct_distance_m=round(view.direct_distance_m, 1),
        )


class ClientRequest(CamelModel):
    name: str = Field(min_length=2, max_length=160)
    tax_id: str | None = Field(default=None, max_length=30)
    contact_email: str | None = Field(default=None, max_length=254)


class ClientResponse(CamelModel):
    id: uuid.UUID
    name: str
    tax_id: str | None
    contact_email: str | None

    @classmethod
    def from_entity(cls, client: Client) -> ClientResponse:
        return cls(id=client.id, name=client.name, tax_id=client.tax_id, contact_email=client.contact_email)


class GeofenceRequest(CamelModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    boundary: list[Coordinates] = Field(min_length=3, max_length=500)


class GeofenceResponse(CamelModel):
    id: uuid.UUID
    code: str
    name: str
    kind: str
    boundary: list[Coordinates]

    @classmethod
    def from_entity(cls, geofence: Geofence) -> GeofenceResponse:
        return cls(
            id=geofence.id,
            code=geofence.code,
            name=geofence.name,
            kind=geofence.kind.value,
            boundary=[Coordinates(latitude=p.latitude, longitude=p.longitude) for p in geofence.boundary],
        )


class GeocodingResultResponse(CamelModel):
    id: str
    display_name: str
    latitude: float
    longitude: float
    category: str | None = None
    result_type: str | None = None
