from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class IoTDeviceModel(Base):
    __tablename__ = "iot_devices"
    __table_args__ = (
        # La BD garantiza "como máximo un gateway de telemetría activo por vehículo".
        Index(
            "uq_iot_devices_one_gateway_per_vehicle",
            "vehicle_id",
            unique=True,
            postgresql_where=text("device_type = 'edge_gateway' AND is_active AND vehicle_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True)
    device_type: Mapped[str] = mapped_column(String(20))
    serial_number: Mapped[str] = mapped_column(String(60))
    firmware_version: Mapped[str] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL"), index=True
    )
    last_connection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
