"""Modelos ORM del contexto de viajes (representación en BD, no son objetos de dominio)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base

trip_notification_recipients = Table(
    "trip_notification_recipients",
    Base.metadata,
    Column("trip_id", UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), primary_key=True),
    Column("recipient_id", UUID(as_uuid=True), ForeignKey("notification_recipients.id"), primary_key=True),
)


class TripModel(Base):
    __tablename__ = "trips"
    __table_args__ = (
        # Un vehículo / conductor puede estar en un solo viaje en curso (lo garantiza la BD).
        Index("uq_trips_ongoing_vehicle", "vehicle_id", unique=True, postgresql_where=text("status = 'ongoing'")),
        Index("uq_trips_ongoing_driver", "driver_id", unique=True, postgresql_where=text("status = 'ongoing'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vehicles.id"), index=True)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drivers.id"), index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("iot_devices.id"))
    client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"))
    origin_label: Mapped[str] = mapped_column(String(300))
    origin: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326))
    destination_label: Mapped[str] = mapped_column(String(300))
    destination: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326))
    cargo_description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), index=True)
    monitoring_configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Bloqueo optimista: dos "iniciar"/"terminar" a la vez sobre el mismo viaje no pueden ganar los dos.
    __mapper_args__ = {"version_id_col": version}


class ClientModel(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    tax_id: Mapped[str | None] = mapped_column(String(30))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GeofenceModel(Base):
    __tablename__ = "geofences"
    __table_args__ = (
        Index(
            "uq_geofences_destination_per_trip", "trip_id", unique=True, postgresql_where=text("kind = 'destination'")
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    trip_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"))
    area: Mapped[Any] = mapped_column(Geometry("POLYGON", srid=4326))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MonitoringDefaultsModel(Base):
    """Tabla de una sola fila con la configuración de monitoreo por defecto para viajes nuevos."""

    __tablename__ = "monitoring_defaults"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
