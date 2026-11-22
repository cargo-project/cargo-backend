"""Importa todos los modelos ORM para que Base.metadata esté completo (lo usan Alembic y los tests)."""

from __future__ import annotations

from app.infrastructure.database import audit_log_model
from app.infrastructure.database.base import Base
from app.infrastructure.messaging import outbox_model
from app.modules.configuration.infrastructure import settings_persistence
from app.modules.fleet.infrastructure.persistence import (
    assignment_models,
    driver_model,
    iot_device_model,
    vehicle_model,
)
from app.modules.identity.infrastructure.persistence import user_model
from app.modules.monitoring.infrastructure.persistence import monitoring_models
from app.modules.notifications.infrastructure.persistence import notification_models
from app.modules.trips.infrastructure.persistence import trip_models

ALL_MODEL_MODULES = (
    audit_log_model,
    outbox_model,
    settings_persistence,
    assignment_models,
    driver_model,
    iot_device_model,
    vehicle_model,
    user_model,
    monitoring_models,
    notification_models,
    trip_models,
)

metadata = Base.metadata
