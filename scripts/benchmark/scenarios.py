"""Catálogo de escenarios reproducibles para las 5 reglas CEP.

Cada escenario usa su propio viaje (trip_id) y declara:
* la configuración del viaje que recibe Siddhi en trip/started (umbrales),
* los pasos: lecturas de telemetry/enriched o pausas reales (para la regla de ausencia),
* los eventos que DEBEN detectarse (conteo por tipo). Lo que no esté declarado debe salir 0.

Los tiempos de las lecturas (event_time) van comprimidos: una lectura por segundo de event_time
aunque se manden casi seguidas, así una ventana de 3 s se prueba sin esperar. La pérdida de
comunicación sí necesita esperar de verdad, porque Siddhi la mide con el reloj (trigger cada 5 s).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Umbrales base acortados (mismas reglas, tiempos chicos). Se envían a Siddhi en trip/started.
BASE_CONFIG: dict[str, Any] = {
    "deviation_min_events": 3,
    "deviation_min_increase_m": 300.0,
    "deviation_window_ms": 2000,
    "stop_speed_kmh": 3.0,
    "stop_max_displacement_m": 20.0,
    "stop_duration_ms": 3000,
    "connection_loss_ms": 600_000,  # apagada salvo en los escenarios de conectividad
    "arrival_confirmation_ms": 1500,
}

# Lectura "normal": en movimiento, lejos del destino, acercándose.
BASE_READING: dict[str, Any] = {
    "latitude": -12.1,
    "longitude": -77.0,
    "speed_kmh": 60.0,
    "kind": "POSITION",
    "temporal_classification": "LIVE",
    "moving_away_m": 0.0,
    "distance_to_destination_m": 50_000.0,
    "inside_destination": False,
    "displacement_window_m": 900.0,
}


@dataclass
class Step:
    """Una lectura (fields) o una pausa real en segundos (pause_s)."""

    fields: dict[str, Any] | None = None
    pause_s: float = 0.0
    dt_ms: int = 1000  # avance del event_time respecto de la lectura anterior


@dataclass
class Scenario:
    id: str
    rule: str
    category: str  # positive | negative | boundary | connectivity
    description: str
    steps: list[Step]
    expected: dict[str, int] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    end_trip_first: bool = False

    def trip_config(self) -> dict[str, Any]:
        return {**BASE_CONFIG, **self.config}


def readings(n: int, dt_ms: int = 1000, **fields: Any) -> list[Step]:
    return [Step(fields=dict(fields), dt_ms=dt_ms) for _ in range(n)]


def pause(seconds: float) -> list[Step]:
    return [Step(pause_s=seconds)]


DEV, STOP, ARR, CONN, EMG = "ROUTE_DEVIATION", "PROLONGED_STOP", "DESTINATION_ARRIVAL", "CONNECTION_LOSS", "EMERGENCY"
FAST_LOSS = {"connection_loss_ms": 6000}


def catalog() -> list[Scenario]:
    return [
        # ------------------------------------------------------------- ROUTE_DEVIATION (alejarse del destino)
        Scenario(
            "DEV-P1",
            DEV,
            "positive",
            "Se aleja 450 m (> 300) durante 5 lecturas / 4 s",
            readings(5, moving_away_m=450.0),
            {DEV: 1},
        ),
        Scenario(
            "DEV-B1",
            DEV,
            "boundary",
            "Alejamiento exactamente igual al umbral (300 m): la regla usa >",
            readings(5, moving_away_m=300.0),
        ),
        Scenario(
            "DEV-B2",
            DEV,
            "boundary",
            "301 m con el mínimo justo: 3 lecturas y 2000 ms (= ventana)",
            readings(3, moving_away_m=301.0),
            {DEV: 1},
        ),
        Scenario(
            "DEV-N1",
            DEV,
            "negative",
            "Ida y vuelta corta: 120 m (< 300), ruido o desvío breve",
            readings(6, moving_away_m=120.0),
        ),
        Scenario(
            "DEV-N2",
            DEV,
            "negative",
            "Solo 2 lecturas alejándose y vuelve a acercarse",
            readings(2, moving_away_m=450.0) + readings(3, moving_away_m=50.0),
        ),
        Scenario(
            "DEV-N3",
            DEV,
            "connectivity",
            "Ráfaga store-and-forward (DELAYED) alejándose: una alerta durante desconexión",
            readings(5, moving_away_m=900.0, temporal_classification="DELAYED"),
            {DEV: 1},
        ),
        Scenario(
            "DEV-R1",
            DEV,
            "positive",
            "Dos episodios separados: alerta, se acerca (reinicia) y vuelve a alejarse",
            readings(3, moving_away_m=450.0) + readings(1, moving_away_m=50.0) + readings(3, moving_away_m=450.0),
            {DEV: 2},
        ),
        # ------------------------------------------------------------- PROLONGED_STOP
        Scenario(
            "STOP-P1",
            STOP,
            "positive",
            "Detenido 4 s (> 3 s) con desplazamiento 4 m",
            readings(5, speed_kmh=0.0, displacement_window_m=4.0),
            {STOP: 1},
        ),
        Scenario(
            "STOP-B1",
            STOP,
            "boundary",
            "Detenido exactamente 3000 ms (= duración)",
            readings(4, speed_kmh=0.0, displacement_window_m=4.0),
            {STOP: 1},
        ),
        Scenario(
            "STOP-N1",
            STOP,
            "negative",
            "Detenido solo 2000 ms (< 3000)",
            readings(3, speed_kmh=0.0, displacement_window_m=4.0),
        ),
        Scenario(
            "STOP-N2",
            STOP,
            "negative",
            "Velocidad baja pero se desplazó 30 m (> 20): avanza lento",
            readings(5, speed_kmh=0.0, displacement_window_m=30.0),
        ),
        Scenario(
            "STOP-N3",
            STOP,
            "negative",
            "Detenido DENTRO de la zona de llegada: es llegada, no detención",
            readings(
                6, speed_kmh=0.0, displacement_window_m=2.0, inside_destination=True, distance_to_destination_m=30.0
            ),
            {ARR: 1},
        ),
        # ------------------------------------------------------------- DESTINATION_ARRIVAL
        Scenario(
            "ARR-P1",
            ARR,
            "positive",
            "3 lecturas dentro de la zona durante 2 s (> 1,5 s)",
            readings(3, inside_destination=True, distance_to_destination_m=40.0, speed_kmh=5.0),
            {ARR: 1},
        ),
        Scenario(
            "ARR-B1",
            ARR,
            "boundary",
            "2 lecturas dentro separadas exactamente 1500 ms (= confirmación)",
            readings(2, dt_ms=1500, inside_destination=True, distance_to_destination_m=40.0, speed_kmh=5.0),
            {ARR: 1},
        ),
        Scenario(
            "ARR-N1",
            ARR,
            "negative",
            "Entra con 1 lectura y sale antes de confirmar",
            readings(1, inside_destination=True, distance_to_destination_m=40.0)
            + readings(3, inside_destination=False, distance_to_destination_m=400.0),
        ),
        Scenario(
            "ARR-N2",
            ARR,
            "negative",
            "Entra y sale alternando: nunca 2 lecturas seguidas dentro",
            readings(1, inside_destination=True, distance_to_destination_m=40.0)
            + readings(1, inside_destination=False, distance_to_destination_m=300.0)
            + readings(1, inside_destination=True, distance_to_destination_m=40.0)
            + readings(1, inside_destination=False, distance_to_destination_m=300.0),
        ),
        # ------------------------------------------------------------- CONNECTION_LOSS (ausencia, tiempo real)
        Scenario(
            "CONN-P1",
            CONN,
            "positive",
            "Una lectura y silencio 14 s (umbral 6 s)",
            readings(1) + pause(14),
            {CONN: 1},
            FAST_LOSS,
        ),
        Scenario(
            "CONN-N1",
            CONN,
            "negative",
            "Conexión estable: una lectura por segundo durante 12 s",
            [s for _ in range(12) for s in readings(1) + pause(1)],
            {},
            FAST_LOSS,
        ),
        Scenario(
            "CONN-R1",
            CONN,
            "connectivity",
            "Corte de 12 s y recuperación (5 lecturas): una sola alerta",
            readings(1) + pause(12) + [s for _ in range(5) for s in readings(1) + pause(1)],
            {CONN: 1},
            FAST_LOSS,
        ),
        # ------------------------------------------------------------- EMERGENCY
        Scenario(
            "EMG-P1",
            EMG,
            "positive",
            "Botón de pánico en una lectura LIVE",
            readings(1, kind="EMERGENCY", speed_kmh=0.0),
            {EMG: 1},
        ),
        Scenario(
            "EMG-P2",
            EMG,
            "connectivity",
            "Botón de pánico que llega tarde (DELAYED): igual alerta",
            readings(1, kind="EMERGENCY", temporal_classification="DELAYED"),
            {EMG: 1},
        ),
        Scenario("EMG-N1", EMG, "negative", "Lecturas normales sin botón", readings(5)),
        # ------------------------------------------------------------- ciclo de vida
        Scenario(
            "END-N1",
            DEV,
            "negative",
            "Viaje ya terminado: lecturas alejándose no generan nada",
            readings(5, moving_away_m=900.0),
            end_trip_first=True,
        ),
    ]


def expand(scenario: Scenario, trip_id: str, start_ms: int) -> dict[str, Any]:
    """Versión serializable del escenario con las lecturas completas (para guardar las entradas)."""
    t, sequence, steps = start_ms, 0, []
    for step in scenario.steps:
        if step.fields is None:
            steps.append({"pause_s": step.pause_s})
            continue
        sequence += 1
        t += step.dt_ms if sequence > 1 else 0
        reading = {**BASE_READING, **step.fields, "trip_id": trip_id, "sequence": sequence, "event_time_ms": t}
        steps.append({"reading": reading})
    return {
        "id": scenario.id,
        "rule": scenario.rule,
        "category": scenario.category,
        "description": scenario.description,
        "trip_id": trip_id,
        "config": scenario.trip_config(),
        "end_trip_first": scenario.end_trip_first,
        "expected": scenario.expected,
        "steps": steps,
    }
