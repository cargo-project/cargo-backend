from __future__ import annotations

from dataclasses import dataclass

UNKNOWN_DISPLACEMENT = -1.0


@dataclass(frozen=True, slots=True)
class SpatialContext:
    """Datos que saca PostGIS para una posición GNSS.

    Dice dónde está el vehículo respecto a su destino; nunca decide si algo es una
    anomalía (eso lo hace CEP). CarGO no conoce rutas, solo origen y destino:

    * moving_away_m: cuánto más lejos del destino está el vehículo comparado con el punto
      más cercano que ya había alcanzado en el viaje (0 mientras se siga acercando).
      CEP saca una posible desviación cuando se mantiene por encima del umbral del viaje.
    """

    distance_to_destination_m: float
    inside_destination: bool
    moving_away_m: float = 0.0
    displacement_window_m: float = UNKNOWN_DISPLACEMENT
    zone_codes: tuple[str, ...] = ()
