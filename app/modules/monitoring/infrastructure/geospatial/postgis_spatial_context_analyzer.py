"""SpatialContextAnalyzer con PostGIS (una sola consulta por lectura).

Todo el análisis espacial operativo pasa acá, contra los datos de PostgreSQL:
no se llama a ninguna API de mapas por cada posición GNSS.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.monitoring.domain.entities.telemetry_event import TelemetryEvent
from app.modules.monitoring.domain.value_objects.spatial_context import (
    UNKNOWN_DISPLACEMENT,
    SpatialContext,
)

# Con los casts a geography las distancias salen en metros sobre WGS84. No hay ruta:
# todo se calcula respecto al destino del viaje y su zona de llegada.
# closest_m = la menor distancia al destino de las lecturas ANTERIORES del viaje
#             (por event_time); moving_away_m = distancia actual - closest_m (>= 0).
# displacement_window_m = distancia entre esta posición y la primera lectura del viaje
# dentro de los últimos stop_duration_seconds; CEP lo usa para confirmar que un vehículo
# lento de verdad se quedó quieto. Para una lectura LIVE solo cuentan las LIVE; para una
# DELAYED (el tramo sin señal que llega al reconectar) cuentan todas, porque ese tramo
# entero llega atrasado y CEP lo analiza aparte.
_ANALYZE_SQL = text(
    """
    WITH p AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS geom)
    SELECT
      ST_Distance(t.destination::geography, p.geom::geography) AS distance_to_destination_m,
      COALESCE(ST_Covers(dg.area, p.geom), FALSE) AS inside_destination,
      (SELECT min(te.distance_to_destination_m)
         FROM telemetry_events te
        WHERE te.trip_id = t.id
          AND te.id <> :telemetry_id
          AND te.event_time <= :event_time
          AND te.distance_to_destination_m IS NOT NULL) AS closest_m,
      (SELECT ST_Distance(te.position::geography, p.geom::geography)
         FROM telemetry_events te
        WHERE te.trip_id = t.id
          AND (te.temporal_classification = 'LIVE' OR :classification = 'DELAYED')
          AND te.id <> :telemetry_id
          AND te.event_time <= :event_time
          AND te.event_time >= :event_time
              - make_interval(secs => (t.monitoring_configuration ->> 'stop_duration_seconds')::double precision)
        ORDER BY te.event_time ASC
        LIMIT 1) AS displacement_window_m,
      ARRAY(SELECT g.code FROM geofences g
             WHERE g.kind = 'zone' AND ST_Covers(g.area, p.geom) ORDER BY g.code) AS zone_codes
    FROM trips t
    LEFT JOIN geofences dg ON dg.trip_id = t.id AND dg.kind = 'destination'
    CROSS JOIN p
    WHERE t.id = :trip_id
    """
)


class PostgisSpatialContextAnalyzer:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def analyze(self, telemetry: TelemetryEvent) -> SpatialContext:
        row = (
            (
                await self._session.execute(
                    _ANALYZE_SQL,
                    {
                        "lon": telemetry.position.longitude,
                        "lat": telemetry.position.latitude,
                        "trip_id": telemetry.trip_id,
                        "telemetry_id": telemetry.id,
                        "event_time": telemetry.event_time,
                        "classification": telemetry.temporal_classification.value,
                    },
                )
            )
            .mappings()
            .one()
        )
        displacement = row["displacement_window_m"]
        distance = float(row["distance_to_destination_m"])
        closest = row["closest_m"]
        return SpatialContext(
            distance_to_destination_m=distance,
            inside_destination=bool(row["inside_destination"]),
            moving_away_m=max(0.0, distance - float(closest)) if closest is not None else 0.0,
            displacement_window_m=float(displacement) if displacement is not None else UNKNOWN_DISPLACEMENT,
            zone_codes=tuple(row["zone_codes"] or ()),
        )
