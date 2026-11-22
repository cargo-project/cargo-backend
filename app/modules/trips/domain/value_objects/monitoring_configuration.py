from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from typing import Any

from app.modules.trips.domain.exceptions.trip_errors import InvalidMonitoringConfigurationError

# (mín, máx) permitido para cada parámetro. Los límites evitan reglas CEP sin sentido:
# por ejemplo, perder conexión a 1 segundo llenaría al operador de falsas alarmas.
_BOUNDS: dict[str, tuple[float, float]] = {
    "route_deviation_min_events": (2, 100),
    "route_deviation_min_increase_m": (50, 50_000),
    "route_deviation_window_seconds": (0, 86_400),
    "stop_speed_kmh": (0, 30),
    "stop_max_displacement_m": (1, 2_000),
    "stop_duration_seconds": (60, 86_400),
    "connection_loss_seconds": (30, 86_400),
    "arrival_radius_m": (20, 5_000),
    "arrival_confirmation_seconds": (0, 3_600),
    "sequence_gap_wait_seconds": (0, 86_400),
}

# Claves que guardaban versiones anteriores y ya no existen (el corredor de la ruta).
_LEGACY_KEYS = frozenset({"route_deviation_corridor_m"})


@dataclass(frozen=True, slots=True)
class MonitoringConfiguration:
    """Umbrales por viaje que usan las reglas CEP.

    La posible desviación no se compara con ninguna ruta: CarGO solo conoce origen y
    destino. Salta cuando el vehículo se aleja del destino, es decir, cuando su distancia
    al destino supera la más cercana que ya había alcanzado en más de
    route_deviation_min_increase_m, durante al menos route_deviation_min_events lecturas
    seguidas y al menos route_deviation_window_seconds.

    Es inmutable: un cambio genera un valor nuevo (with_changes) que el viaje valida y
    publica como trip/config-updated.

    sequence_gap_wait_seconds se mantiene por compatibilidad con el frontend; en v2 CEP
    no reordena secuencias (solo evalúa LIVE), así que ninguna regla lo usa.
    """

    route_deviation_min_events: int = 3
    route_deviation_min_increase_m: float = 300.0
    route_deviation_window_seconds: int = 60
    stop_speed_kmh: float = 3.0
    stop_max_displacement_m: float = 50.0
    stop_duration_seconds: int = 900
    connection_loss_seconds: int = 300
    arrival_radius_m: float = 150.0
    arrival_confirmation_seconds: int = 60
    sequence_gap_wait_seconds: int = 1_800

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            low, high = _BOUNDS[field.name]
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise InvalidMonitoringConfigurationError(f"{field.name} debe ser numérico.")
            if not low <= value <= high:
                raise InvalidMonitoringConfigurationError(
                    f"{field.name} debe estar entre {low:g} y {high:g}.",
                    details={"field": field.name, "value": value, "min": low, "max": high},
                )

    @classmethod
    def from_stored(cls, values: dict[str, Any]) -> MonitoringConfiguration:
        """Reconstruye una configuración guardada, ignorando claves de versiones anteriores."""
        return cls(**{key: value for key, value in values.items() if key not in _LEGACY_KEYS})

    def with_changes(self, **changes: Any) -> MonitoringConfiguration:
        unknown = set(changes) - set(_BOUNDS)
        if unknown:
            raise InvalidMonitoringConfigurationError(f"Parámetros desconocidos: {sorted(unknown)}")
        return replace(self, **changes)

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)
