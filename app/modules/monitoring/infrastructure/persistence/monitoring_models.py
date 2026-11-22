from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class TelemetryEventModel(Base):
    """Una lectura GNSS. La idempotencia la aseguran dos constraints únicas:
    message_id y (trip_id, sequence).
    """

    __tablename__ = "telemetry_events"
    __table_args__ = (
        UniqueConstraint("trip_id", "sequence", name="uq_telemetry_events_trip_sequence"),
        Index("ix_telemetry_events_trip_event_time", "trip_id", "event_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iot_devices.id"))
    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id"))
    sequence: Mapped[int] = mapped_column(BigInteger)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    position: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    speed_kmh: Mapped[float] = mapped_column(Float)
    kind: Mapped[str] = mapped_column(String(16))
    temporal_classification: Mapped[str] = mapped_column(String(10))
    distance_to_destination_m: Mapped[float | None] = mapped_column(Float)
    # Cuánto se pasó de la distancia más cercana al destino ya alcanzada (entrada de la desviación).
    moving_away_m: Mapped[float | None] = mapped_column(Float)
    inside_destination: Mapped[bool | None] = mapped_column(Boolean)
    displacement_window_m: Mapped[float | None] = mapped_column(Float)
    zone_codes: Mapped[list[str] | None] = mapped_column(ARRAY(String(48)))
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MonitoringEventModel(Base):
    __tablename__ = "monitoring_events"
    __table_args__ = (Index("ix_monitoring_events_trip_detected", "trip_id", "detected_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id"))
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    position: Mapped[Any | None] = mapped_column(Geometry("POINT", srid=4326))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MonitoringEventEvidenceModel(Base):
    __tablename__ = "monitoring_event_evidence"

    monitoring_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitoring_events.id", ondelete="CASCADE"), primary_key=True
    )
    telemetry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("telemetry_events.id"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(BigInteger)
