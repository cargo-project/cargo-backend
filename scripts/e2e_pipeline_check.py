"""Prueba de punta a punta sobre la plataforma levantada con Docker Compose.

Hace de dos dispositivos Edge (MQTT sobre TLS, credenciales por dispositivo) y de
cliente web (REST + WebSocket). Revisa: ingesta, deduplicación, LIVE/DELAYED
(store-and-forward), enriquecimiento PostGIS, detecciones de Siddhi (ROUTE_DEVIATION,
EMERGENCY, CONNECTION_LOSS, DESTINATION_ARRIVAL), cierre automático del viaje,
MonitoringEvent con evidencia, trazabilidad de notificaciones y avisos por WebSocket.

Uso:  python -m scripts.e2e_pipeline_check                 (lee el .env; necesita docker compose up + seed)
      python -m scripts.e2e_pipeline_check --export DIR     (además guarda tiempos por etapa en CSV/JSON)
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import paho.mqtt.client as mqtt
import websockets

API = os.environ.get("E2E_API", "http://127.0.0.1:8000/api/v1")
WS = API.replace("http", "ws") + "/ws"
ORIGIN = (-12.0464, -77.0428)
DESTINATION = (-12.0700, -77.0428)  # ~2,6 km al sur
results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"[{'OK ' if condition else 'FAIL'}] {name} {detail}")  # noqa: T201 - reporte por consola


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


class Device:
    def __init__(self, code: str, password: str, ca_file: str) -> None:
        self.code = code
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{code}-e2e-{uuid.uuid4().hex[:4]}")
        self.client.username_pw_set(code, password)
        context = ssl.create_default_context(cafile=ca_file)
        self.client.tls_set_context(context)
        self.client.connect("127.0.0.1", 8883)
        self.client.loop_start()
        self.sequence = 0

    def reading(
        self,
        trip_id: str,
        lat: float,
        lon: float,
        *,
        speed: float = 50.0,
        emergency: bool = False,
        event_time: datetime | None = None,
    ) -> dict[str, Any]:
        self.sequence += 1
        return {
            "message_id": str(uuid.uuid4()),
            "device_id": self.code,
            "trip_id": trip_id,
            "sequence": self.sequence,
            "event_time": (event_time or datetime.now(UTC)).isoformat(),
            "latitude": lat,
            "longitude": lon,
            "speed_kmh": speed,
            "emergency": emergency,
            "schema_version": 1,
        }

    def publish(self, payload: dict[str, Any], topic_code: str | None = None) -> None:
        info = self.client.publish(f"telemetry/raw/{topic_code or self.code}", json.dumps(payload), qos=1)
        info.wait_for_publish(timeout=5)


def fetch_broker_ca() -> str:
    """Copia la CA de desarrollo que se genera dentro del contenedor del broker IoT."""
    ca_dir = tempfile.mkdtemp()
    command = ["docker", "compose", "cp", "mqtt-iot:/mosquitto/certs/ca.crt", ca_dir]
    subprocess.run(command, check=True, capture_output=True)  # noqa: S603 - comando fijo de desarrollo
    return str(Path(ca_dir) / "ca.crt")


async def export_results(export_dir: Path, trip_codes: list[str], ws_messages: list[dict[str, Any]]) -> None:
    """Deja los checks, los avisos WebSocket y los tiempos por etapa (desde la BD) en export_dir."""
    from scripts.benchmark.export_pipeline_metrics import export

    export_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240 - archivos chicos, al final de la prueba
    (export_dir / "e2e_checks.json").write_text(
        json.dumps([{"check": n, "ok": ok, "detail": d} for n, ok, d in results], indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    receipts = [
        {
            "event_id": m["eventId"],
            "event_type": m.get("eventType"),
            "trip_code": m.get("tripId"),
            "received_ms": m["_received_ms"],
        }
        for m in ws_messages
        if m.get("type") == "monitoring.event_created" and m.get("eventId")
    ]
    (export_dir / "ws_receipts.json").write_text(json.dumps(receipts, indent=1), encoding="utf-8")
    await export(export_dir, trip_codes=trip_codes, ws_receipts=receipts)
    print(f"tiempos por etapa exportados en {export_dir}")  # noqa: T201


async def main(ca_file: str, export_dir: Path | None = None) -> int:
    env = load_env()
    accounts = dict(item.split(":", 1) for item in env["MQTT_IOT_DEVICE_ACCOUNTS"].split(","))

    async with httpx.AsyncClient(base_url=API, timeout=20) as http:
        login = await http.post(
            "/auth/login", json={"email": env["SEED_ADMIN_EMAIL"], "password": env["SEED_ADMIN_PASSWORD"]}
        )
        check("login", login.status_code == 200)
        csrf = {"X-CSRF-Token": http.cookies["cargo_csrf"]}
        cookie_header = "; ".join(f"{k}={v}" for k, v in http.cookies.items())

        ws_messages: list[dict[str, Any]] = []

        async def listen() -> None:
            async with websockets.connect(
                WS, additional_headers={"Cookie": cookie_header, "Origin": "http://localhost:3000"}
            ) as socket:
                async for raw in socket:
                    # Guardamos cuándo llegó cada aviso: es el "disponible en la web" del banco.
                    ws_messages.append({**json.loads(raw), "_received_ms": time.time() * 1000})

        listener = asyncio.create_task(listen())
        await asyncio.sleep(1)

        recipient = (await http.get("/notification-recipients")).json()["data"][0]["id"]
        drivers = {d["code"]: d for d in (await http.get("/drivers")).json()["data"]}
        trips: dict[str, dict[str, Any]] = {}
        for vehicle, driver in (("TRK-003", "DRV-001"), ("TRK-011", "DRV-002")):
            if drivers[driver]["status"] != "available":
                print(f"driver {driver} busy; re-run on a fresh database")  # noqa: T201
                return 2
            body = {
                "vehicleCode": vehicle,
                "driverCode": driver,
                "originLabel": "Av. Javier Prado, Lima",
                "origin": {"latitude": ORIGIN[0], "longitude": ORIGIN[1]},
                "destinationLabel": "Almacén Surquillo",
                "cargoDescription": "Prueba E2E",
                "destination": {"latitude": DESTINATION[0], "longitude": DESTINATION[1]},
                "recipientIds": [recipient],
            }
            created = await http.post("/trips", json=body, headers=csrf)
            check(f"create trip {vehicle}", created.status_code == 201, created.text[:120])
            trips[vehicle] = created.json()["data"]
        a, b = trips["TRK-003"], trips["TRK-011"]
        patch_a = {"routeDeviationWindowSeconds": 0, "routeDeviationMinEvents": 3, "arrivalConfirmationSeconds": 0}
        await http.patch(f"/trips/{a['code']}/monitoring-config", json=patch_a, headers=csrf)
        await http.patch(f"/trips/{b['code']}/monitoring-config", json={"connectionLossSeconds": 30}, headers=csrf)
        for trip in (a, b):
            started = await http.post(f"/trips/{trip['code']}/start", headers=csrf)
            check(f"start {trip['code']}", started.json()["data"]["status"] == "ongoing")
        await asyncio.sleep(3)  # CEP recibe trip/started a través del outbox

        dev_a = Device("DEV-GW-003", accounts["DEV-GW-003"], ca_file)
        dev_b = Device("DEV-GW-011", accounts["DEV-GW-011"], ca_file)
        await asyncio.sleep(1)

        # 1) lecturas en vivo hacia el destino, más una reentrega QoS 1 de una de ellas
        live = [dev_a.reading(a["id"], ORIGIN[0] - 0.002 * i, ORIGIN[1]) for i in range(1, 6)]
        for item in live:
            dev_a.publish(item)
            await asyncio.sleep(0.3)
        dev_a.publish(live[2])  # message_id duplicado
        # 2) lecturas generadas "sin conexión": se guardan en el dispositivo y se mandan después
        buffered = [dev_a.reading(a["id"], ORIGIN[0] - 0.011, ORIGIN[1]) for _ in range(3)]
        # 3) la ACL tiene que impedir que un dispositivo publique en el topic de otro
        blocked = dev_a.reading(b["id"], -12.1, -77.1)
        dev_a.publish(blocked, topic_code="DEV-GW-011")
        # 4) viaje B: una lectura y después el botón de pánico
        dev_b.publish(dev_b.reading(b["id"], ORIGIN[0], ORIGIN[1]))
        dev_b.publish(dev_b.reading(b["id"], ORIGIN[0], ORIGIN[1], speed=0, emergency=True))
        # 5) posible desviación: el camión vuelve hacia el norte, alejándose del destino
        #    (>1 km más que el punto más cercano que había alcanzado; umbral 300 m)
        for i in range(4):
            dev_a.publish(dev_a.reading(a["id"], ORIGIN[0] + 0.001 * i, ORIGIN[1]))
            await asyncio.sleep(1)

        print("waiting 70 s: LIVE tolerance for the buffered readings + CONNECTION_LOSS of trip B")  # noqa: T201
        await asyncio.sleep(70)
        for item in buffered:  # ráfaga de store-and-forward al reconectar
            dev_a.publish(item)
        dev_a.publish(live[1])  # otra retransmisión
        # 6) llegada al destino (dos lecturas seguidas dentro de la zona de llegada)
        for _ in range(3):
            dev_a.publish(dev_a.reading(a["id"], DESTINATION[0], DESTINATION[1], speed=4))
            await asyncio.sleep(1.5)
        await asyncio.sleep(8)

        trip_a = (await http.get(f"/trips/{a['code']}")).json()["data"]
        check(
            "trip A completed automatically on DESTINATION_ARRIVAL", trip_a["status"] == "completed", trip_a["status"]
        )
        telemetry = (await http.get(f"/trips/{a['code']}/telemetry?limit=100")).json()["data"]
        sequences = sorted(t["sequenceNumber"] for t in telemetry)
        expected = sorted(set(range(1, dev_a.sequence + 1)) - {blocked["sequence"]})
        check(
            "deduplication: each measurement stored exactly once (2 redeliveries ignored)",
            sequences == expected,
            f"stored={len(telemetry)} expected={len(expected)}",
        )
        by_seq = {t["sequenceNumber"]: t for t in telemetry}
        check(
            "store-and-forward readings classified DELAYED",
            all(by_seq[b_["sequence"]]["temporalClassification"] == "DELAYED" for b_ in buffered),
        )
        check("live readings classified LIVE", by_seq[1]["temporalClassification"] == "LIVE")
        check(
            "event_time preserved for delayed readings",
            by_seq[buffered[0]["sequence"]]["eventTime"][:19] == buffered[0]["event_time"][:19],
        )
        check(
            "PostGIS enrichment (distance to destination, moving away)",
            by_seq[1]["distanceToDestinationM"] > 0 and by_seq[1]["movingAwayM"] == 0,
            f"{by_seq[1]['distanceToDestinationM']} / {by_seq[1]['movingAwayM']}",
        )
        check("ACL blocked cross-device publication", all(t["deviceCode"] == "DEV-GW-003" for t in telemetry))

        events_a = (await http.get(f"/events?trip_code={a['code']}")).json()["data"]
        types_a = sorted(e["type"] for e in events_a)
        check("trip A events", types_a == ["DESTINATION_ARRIVAL", "ROUTE_DEVIATION", "TRIP_STARTED"], str(types_a))
        deviation = next((e for e in events_a if e["type"] == "ROUTE_DEVIATION"), None)
        check("deviation has evidence telemetry", bool(deviation and len(deviation["evidence"]) >= 3))
        events_b = (await http.get(f"/events?trip_code={b['code']}")).json()["data"]
        types_b = sorted(e["type"] for e in events_b)
        check("trip B events", types_b == ["CONNECTION_LOSS", "EMERGENCY", "TRIP_STARTED"], str(types_b))
        emergency = next((e for e in events_b if e["type"] == "EMERGENCY"), None)
        check("emergency is CRITICAL", bool(emergency and emergency["severity"] == "CRITICAL"))
        check(
            "notification attempt traced (sent / skipped / failed recorded)",
            bool(
                emergency
                and emergency["notifications"]
                and emergency["notifications"][0]["status"] in {"skipped", "sent", "failed"}
            ),
            str(emergency and emergency["notifications"]),
        )
        if deviation:
            latency = (
                datetime.fromisoformat(deviation["detectedAt"]) - datetime.fromisoformat(deviation["eventTime"])
            ).total_seconds()
            check("detection latency (event_time -> detected_at) < 5 s", latency < 5, f"{latency:.2f}s")

        await http.post(f"/trips/{b['code']}/finish", headers=csrf)
        await asyncio.sleep(1)
        listener.cancel()
        types = {m["type"] for m in ws_messages}
        check(
            "WebSocket pushed position/event/trip updates",
            {"position.updated", "monitoring.event_created", "trip.status_changed"} <= types,
            str(sorted(types)),
        )
        devices = {d["code"]: d for d in (await http.get("/devices")).json()["data"]}
        check("device online after telemetry", devices["DEV-GW-003"]["status"] == "online")
        dev_a.client.loop_stop()
        dev_b.client.loop_stop()

    if export_dir is not None:
        await export_results(export_dir, [a["code"], b["code"]], ws_messages)
    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")  # noqa: T201
    return 1 if failed else 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prueba de punta a punta sobre la plataforma Docker.")
    parser.add_argument("--export", type=Path, default=None, help="carpeta para guardar tiempos por etapa (CSV/JSON)")
    arguments = parser.parse_args()
    started = time.monotonic()
    code = asyncio.run(main(fetch_broker_ca(), arguments.export))
    print(f"elapsed {time.monotonic() - started:.0f}s")  # noqa: T201
    sys.exit(code)
