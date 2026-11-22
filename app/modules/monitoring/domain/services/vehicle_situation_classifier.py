from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class VehicleSituation(StrEnum):
    ALERT = "alert"
    NO_CONNECTION = "no_connection"
    STOPPED = "stopped"
    ON_ROUTE = "on_route"


@dataclass(frozen=True, slots=True)
class VehicleSnapshot:
    has_pending_alert: bool
    last_signal_at: datetime | None
    speed_kmh: float | None
    connection_loss_threshold: timedelta
    stop_speed_kmh: float


class VehicleSituationClassifier:
    """Resumen para el dashboard (supervisión por excepción).

    Prioridad: alerta sin revisar > sin señal reciente > detenido > en ruta.
    """

    def classify(self, snapshot: VehicleSnapshot, now: datetime) -> VehicleSituation:
        if snapshot.has_pending_alert:
            return VehicleSituation.ALERT
        if snapshot.last_signal_at is None or now - snapshot.last_signal_at > snapshot.connection_loss_threshold:
            return VehicleSituation.NO_CONNECTION
        if snapshot.speed_kmh is not None and snapshot.speed_kmh <= snapshot.stop_speed_kmh:
            return VehicleSituation.STOPPED
        return VehicleSituation.ON_ROUTE
