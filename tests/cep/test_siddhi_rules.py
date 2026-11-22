"""Comportamiento de las reglas CEP corriendo en el runtime real de Siddhi 5.x.

Necesita el contenedor CEP y un broker en TEST_CEP_MQTT_HOST:TEST_CEP_MQTT_PORT
(se levantan con scripts/run_test_infra.ps1). Los umbrales se acortan por viaje, que es
justo lo que permite la configuración por viaje.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time
import uuid
from collections import defaultdict
from typing import Any

import aiomqtt
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.cep]

HOST = os.environ.get("TEST_CEP_MQTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("TEST_CEP_MQTT_PORT", "51884"))


def _available() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=1):
            return True
    except OSError:
        return False


def _config(**overrides: Any) -> dict[str, Any]:
    config = {
        "deviation_min_events": 3,
        "deviation_min_increase_m": 300.0,
        "deviation_window_ms": 2000,
        "stop_speed_kmh": 3.0,
        "stop_max_displacement_m": 20.0,
        "stop_duration_ms": 3000,
        "connection_loss_ms": 600_000,
        "arrival_confirmation_ms": 1500,
    }
    config.update(overrides)
    return config


def _reading(trip_id: str, sequence: int, t_ms: int, **overrides: Any) -> dict[str, Any]:
    reading = {
        "trip_id": trip_id,
        "sequence": sequence,
        "event_time_ms": t_ms,
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
    reading.update(overrides)
    return reading


async def test_cep_rules_end_to_end() -> None:
    if not _available():
        pytest.skip(f"CEP broker not reachable at {HOST}:{PORT}")
    detected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    trips = {
        name: str(uuid.uuid4())
        for name in (
            "deviation",
            "stop",
            "arrival",
            "connection",
            "emergency",
            "delayed",
            "ended",
            "unloading",
            "approaching",
            "bouncing",
            "reentry",
            "gap_stop",
            "alerted_live",
        )
    }
    now = int(time.time() * 1000)

    async with aiomqtt.Client(HOST, PORT, identifier=f"cep-test-{uuid.uuid4().hex[:6]}") as client:
        await client.subscribe("events/detected", qos=1)

        async def collect() -> None:
            async for message in client.messages:
                body = json.loads(message.payload)  # type: ignore[arg-type]
                # Siddhi manda una lista cuando varias detecciones salen en el mismo ciclo.
                for item in body if isinstance(body, list) else [body]:
                    event = item.get("event", item)
                    detected[event["trip_id"]].append(event)

        collector = asyncio.create_task(collect())

        async def publish(topic: str, payload: dict[str, Any]) -> None:
            await client.publish(topic, json.dumps(payload), qos=1)

        # Calentamiento: Siddhi dice "deployed" antes de que todas las fuentes MQTT estén suscritas;
        # con un broker nuevo (sin sesiones persistentes) se perderían los primeros mensajes. Esperamos
        # a que respondan la fuente de control (trip/started -> CONNECTION_LOSS) y la de telemetría (EMERGENCY).
        probe_trip = str(uuid.uuid4())
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and {"CONNECTION_LOSS", "EMERGENCY"} - {
            e["event_type"] for e in detected[probe_trip]
        }:
            await publish(
                "trip/started", {"trip_id": probe_trip, "trip_code": "PROBE", **_config(connection_loss_ms=1000)}
            )
            await publish("telemetry/enriched", _reading(probe_trip, 0, now, kind="EMERGENCY"))
            await asyncio.sleep(3)
        assert {"CONNECTION_LOSS", "EMERGENCY"} <= {e["event_type"] for e in detected[probe_trip]}, "CEP not ready"
        now = int(time.time() * 1000)

        await publish(
            "trip/started", {"trip_id": trips["connection"], "trip_code": "T-CONN", **_config(connection_loss_ms=6000)}
        )
        for name in (
            "deviation",
            "stop",
            "arrival",
            "delayed",
            "ended",
            "unloading",
            "approaching",
            "bouncing",
            "reentry",
            "gap_stop",
            "alerted_live",
        ):
            await publish("trip/started", {"trip_id": trips[name], "trip_code": name, **_config()})
        await asyncio.sleep(1.5)

        # ROUTE_DEVIATION: 5 lecturas seguidas alejándose del destino (450 m más que el punto
        # más cercano, umbral 300 m) -> exactamente una alerta.
        for seq in range(1, 6):
            await publish(
                "telemetry/enriched",
                _reading(trips["deviation"], seq, now + seq * 1000, moving_away_m=450.0 + seq),
            )
        # PROLONGED_STOP: quieto 4 s con desplazamiento mínimo.
        for seq in range(1, 6):
            await publish(
                "telemetry/enriched",
                _reading(trips["stop"], seq, now + seq * 1000, speed_kmh=0.0, displacement_window_m=4.0),
            )
        # DESTINATION_ARRIVAL: 3 lecturas dentro de la zona de llegada en 2 s.
        for seq in range(1, 4):
            await publish(
                "telemetry/enriched",
                _reading(
                    trips["arrival"], seq, now + seq * 1000, inside_destination=True, distance_to_destination_m=40.0
                ),
            )
        # Salir de la zona reinicia la confirmación: rozar el borde (dentro, fuera, dentro, fuera)
        # nunca suma 2 lecturas seguidas dentro -> sin llegada. Si después vuelve a entrar y se
        # queda, la llegada se cuenta desde la reentrada (lectura 3), no desde la primera vez.
        bouncing = [True, False, True, False]
        reentry = [True, False, True, True, True]
        for name, pattern in (("bouncing", bouncing), ("reentry", reentry)):
            for seq, inside in enumerate(pattern, start=1):
                await publish(
                    "telemetry/enriched",
                    _reading(
                        trips[name],
                        seq,
                        now + seq * 1000,
                        speed_kmh=5.0,
                        inside_destination=inside,
                        distance_to_destination_m=40.0 if inside else 300.0,
                    ),
                )
        # Detenido DENTRO del destino más tiempo que stop_duration: eso es la llegada
        # (descargando), nunca un PROLONGED_STOP.
        for seq in range(1, 7):
            await publish(
                "telemetry/enriched",
                _reading(
                    trips["unloading"],
                    seq,
                    now + seq * 1000,
                    speed_kmh=0.0,
                    displacement_window_m=2.0,
                    inside_destination=True,
                    distance_to_destination_m=30.0,
                ),
            )
        # Un ida y vuelta chico debajo del umbral (ruido del GPS, un desvío corto) no es desviación.
        for seq in range(1, 7):
            await publish(
                "telemetry/enriched",
                _reading(trips["approaching"], seq, now + seq * 1000, moving_away_m=120.0),
            )
        # Lo que pasó sin señal llega después (store-and-forward, DELAYED). No toca el seguimiento
        # en vivo, pero se analiza aparte: alejarse del destino durante el corte da UNA desviación
        # marcada delayed ("durante desconexión"), con los tiempos reales del dispositivo.
        for seq in range(1, 6):
            await publish(
                "telemetry/enriched",
                _reading(
                    trips["delayed"],
                    seq,
                    now - 3_600_000 + seq * 1000,
                    moving_away_m=900.0,
                    temporal_classification="DELAYED",
                ),
            )
        # Detenido durante el corte -> una detención prolongada marcada delayed.
        for seq in range(1, 6):
            await publish(
                "telemetry/enriched",
                _reading(
                    trips["gap_stop"],
                    seq,
                    now - 600_000 + seq * 1000,
                    speed_kmh=0.0,
                    displacement_window_m=4.0,
                    temporal_classification="DELAYED",
                ),
            )
        # Desviación ya alertada en vivo y la señal se corta mientras sigue alejándose: el tramo
        # atrasado es el mismo episodio, así que no se repite la alerta.
        for seq in range(1, 6):
            await publish(
                "telemetry/enriched",
                _reading(trips["alerted_live"], seq, now + seq * 1000, moving_away_m=500.0 + seq),
            )
        await asyncio.sleep(1)
        for seq in range(6, 11):
            await publish(
                "telemetry/enriched",
                _reading(
                    trips["alerted_live"],
                    seq,
                    now + seq * 1000,
                    moving_away_m=500.0 + seq,
                    temporal_classification="DELAYED",
                ),
            )
        # EMERGENCY (aunque llegue tarde) sale al instante.
        await publish(
            "telemetry/enriched",
            _reading(trips["emergency"], 1, now, kind="EMERGENCY", temporal_classification="DELAYED"),
        )
        # Un viaje terminado ya no se monitorea.
        await publish("trip/ended", {"trip_id": trips["ended"]})
        await asyncio.sleep(0.5)
        for seq in range(1, 6):
            await publish("telemetry/enriched", _reading(trips["ended"], seq, now + seq * 1000, moving_away_m=900.0))

        await asyncio.sleep(15)  # > connection_loss (6 s) + periodo del trigger (5 s)
        collector.cancel()

    def types(name: str) -> list[str]:
        return [e["event_type"] for e in detected[trips[name]]]

    assert types("deviation") == ["ROUTE_DEVIATION"]
    deviation = detected[trips["deviation"]][0]
    assert deviation["evidence_from_sequence"] == 1 and deviation["evidence_to_sequence"] >= 3
    assert deviation["metric_value"] > 450
    assert types("stop") == ["PROLONGED_STOP"]
    assert detected[trips["stop"]][0]["metric_value"] >= 3.0
    assert types("arrival") == ["DESTINATION_ARRIVAL"]
    assert types("unloading") == ["DESTINATION_ARRIVAL"]  # sin PROLONGED_STOP en el destino
    assert types("bouncing") == []  # nunca 2 lecturas seguidas dentro de la zona
    assert types("reentry") == ["DESTINATION_ARRIVAL"]
    assert detected[trips["reentry"]][0]["evidence_from_sequence"] == 3  # la salida reinició el episodio
    assert types("approaching") == []  # se alejó menos que deviation_min_increase_m
    assert types("connection") == ["CONNECTION_LOSS"]
    assert types("emergency") == ["EMERGENCY"]
    assert detected[trips["emergency"]][0]["delayed"] is True
    assert types("delayed") == ["ROUTE_DEVIATION"]  # una sola, aunque sigan llegando lecturas alejándose
    assert detected[trips["delayed"]][0]["delayed"] is True
    assert detected[trips["delayed"]][0]["evidence_from_sequence"] == 1
    assert types("gap_stop") == ["PROLONGED_STOP"]
    assert detected[trips["gap_stop"]][0]["delayed"] is True
    assert types("alerted_live") == ["ROUTE_DEVIATION"]  # la en vivo; el tramo atrasado no la repite
    assert detected[trips["alerted_live"]][0]["delayed"] is False
    assert types("deviation") == ["ROUTE_DEVIATION"] and deviation["delayed"] is False
    assert types("ended") == []
    assert all(uuid.UUID(e["event_id"]) for events in detected.values() for e in events)
