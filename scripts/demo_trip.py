"""Crea e inicia un viaje corto de prueba usando la API REST (igual que el frontend).

Se usa junto con un dispositivo Edge. Toma el administrador del seed desde el .env.

    python scripts/demo_trip.py                        # TRK-003 / DRV-001, ~2,6 km en Lima
    python scripts/demo_trip.py --vehicle TRK-011 --driver DRV-002 --connection-loss 30
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

ORIGIN = {"latitude": -12.0464, "longitude": -77.0428}
DESTINATION = {"latitude": -12.0700, "longitude": -77.0428}


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--vehicle", default="TRK-003")
    parser.add_argument("--driver", default="DRV-001")
    parser.add_argument("--connection-loss", type=int, default=None, help="seconds (min 30) for this trip")
    parser.add_argument("--deviation-window", type=int, default=None, help="seconds a deviation must persist")
    args = parser.parse_args()
    env = load_env()

    with httpx.Client(base_url=args.api, timeout=20) as http:
        login = http.post(
            "/auth/login", json={"email": env["SEED_ADMIN_EMAIL"], "password": env["SEED_ADMIN_PASSWORD"]}
        )
        login.raise_for_status()
        csrf = {"X-CSRF-Token": http.cookies["cargo_csrf"]}
        recipients = http.get("/notification-recipients").json()["data"]
        if not recipients:
            print("No notification recipients: run the seed first.")  # noqa: T201
            return 1
        body = {
            "vehicleCode": args.vehicle,
            "driverCode": args.driver,
            "originLabel": "Av. Javier Prado, Lima",
            "origin": ORIGIN,
            "destinationLabel": "Almacén Surquillo",
            "destination": DESTINATION,
            "cargoDescription": "Viaje de demostración",
            "recipientIds": [recipients[0]["id"]],
        }
        created = http.post("/trips", json=body, headers=csrf)
        if created.status_code != 201:
            print(f"Trip not created ({created.status_code}): {created.json()['error']['message']}")  # noqa: T201
            return 1
        code = created.json()["data"]["code"]
        changes: dict[str, int] = {}
        if args.connection_loss is not None:
            changes["connectionLossSeconds"] = args.connection_loss
        if args.deviation_window is not None:
            changes["routeDeviationWindowSeconds"] = args.deviation_window
        if changes:
            http.patch(f"/trips/{code}/monitoring-config", json=changes, headers=csrf).raise_for_status()
        started = http.post(f"/trips/{code}/start", headers=csrf)
        if started.status_code != 200:
            print(f"Trip {code} not started: {started.json()['error']['message']}")  # noqa: T201
            return 1
        print(f"Trip {code} started for {args.vehicle} / {args.driver}")  # noqa: T201
        print(f"Detail: http://localhost/viajes/{code}  (or http://localhost:3000/viajes/{code})")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
