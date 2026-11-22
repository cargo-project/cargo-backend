from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration


@dataclass(frozen=True, slots=True)
class CreateTripCommand:
    vehicle_code: str
    driver_code: str
    origin_label: str
    origin_latitude: float
    origin_longitude: float
    destination_label: str
    destination_latitude: float
    destination_longitude: float
    cargo_description: str
    recipient_ids: frozenset[uuid.UUID]
    planned_start_at: datetime | None = None
    client_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class RecipientView:
    id: uuid.UUID
    name: str
    telegram_chat_id: str
    active: bool


@dataclass(frozen=True, slots=True)
class TripView:
    id: uuid.UUID
    code: str
    vehicle_code: str
    plate: str
    driver_code: str
    driver_name: str
    origin_label: str
    origin_latitude: float
    origin_longitude: float
    destination_label: str
    destination_latitude: float
    destination_longitude: float
    cargo_description: str
    status: str
    planned_start_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    progress: int
    monitoring_configuration: MonitoringConfiguration
    direct_distance_m: float  # origen -> destino en línea recta (solo referencia, no es una ruta)
    client_name: str | None = None
    recipients: list[RecipientView] = field(default_factory=list)
