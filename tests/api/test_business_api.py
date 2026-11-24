"""Contratos de las pantallas principales: CRUD de flota, ciclo de viajes, alertas, dashboard y configuración."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI

from app.composition import monitoring_factory
from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.modules.monitoring.application.dto.monitoring_dto import DetectedEventCommand
from tests.api.conftest import ApiClient

pytestmark = pytest.mark.integration


async def _fleet(admin: ApiClient) -> str:
    vehicle = await admin.post(
        "/api/v1/vehicles",
        json={
            "code": "trk-003",
            "plate": "ABC-123",
            "brand": "Volvo",
            "model": "FH16",
            "description": "Tracto",
            "status": "available",
        },
    )
    assert vehicle.status_code == 201, vehicle.text
    assert vehicle.json()["data"]["code"] == "TRK-003"
    driver = await admin.post(
        "/api/v1/drivers",
        json={
            "firstName": "Luis",
            "lastName": "Ramos",
            "document": "70112233",
            "license": "Q70112233",
            "phone": "987654321",
            "status": "available",
        },
    )
    assert driver.status_code == 201
    device = await admin.post(
        "/api/v1/devices",
        json={
            "code": "DEV-GW-003",
            "type": "Edge Gateway",
            "serial": "EGW-PE-90231",
            "firmware": "2.4.1",
            "vehicleCode": "TRK-003",
            "status": "offline",
            "active": True,
        },
    )
    assert device.status_code == 201, device.text
    assert device.json()["data"]["vehicleCode"] == "TRK-003"
    assert device.json()["data"]["status"] == "offline"  # derivado: todavía no se conectó nunca
    recipient = await admin.post(
        "/api/v1/notification-recipients",
        json={"name": "Supervisor Norte", "telegramChatId": "-1001234", "active": True},
    )
    assert recipient.status_code == 201
    return str(driver.json()["data"]["code"])


def _trip_body(driver_code: str, recipient_id: str) -> dict[str, object]:
    return {
        "vehicleCode": "TRK-003",
        "driverCode": driver_code,
        "originLabel": "Lima",
        "origin": {"latitude": -12.0464, "longitude": -77.0428},
        "destinationLabel": "Ica",
        "destination": {"latitude": -14.0678, "longitude": -75.7286},
        "cargoDescription": "Cemento 30 t",
        "recipientIds": [recipient_id],
    }


async def test_fleet_crud_and_validation(admin: ApiClient) -> None:
    await _fleet(admin)
    duplicate = await admin.post(
        "/api/v1/vehicles",
        json={"code": "TRK-003", "plate": "ZZZ-999", "brand": "Volvo", "model": "FH", "status": "available"},
    )
    assert duplicate.status_code == 409
    invalid = await admin.post("/api/v1/vehicles", json={"code": "!", "plate": "x", "brand": "", "model": ""})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    update = await admin.put(
        "/api/v1/vehicles/TRK-003",
        json={
            "code": "TRK-003",
            "plate": "ABC-123",
            "brand": "Volvo",
            "model": "FH16 750",
            "description": "",
            "status": "maintenance",
        },
    )
    assert update.status_code == 200 and update.json()["data"]["status"] == "maintenance"
    on_route = await admin.put(
        "/api/v1/vehicles/TRK-003",
        json={"code": "TRK-003", "plate": "ABC-123", "brand": "Volvo", "model": "FH16", "status": "onRoute"},
    )
    assert on_route.status_code == 422  # solo el ciclo del viaje pone un vehículo en ruta
    assert (await admin.get("/api/v1/vehicles/NOPE")).status_code == 404
    listing = (await admin.get("/api/v1/drivers")).json()["data"]
    assert listing[0]["code"].startswith("DRV-")


async def test_trip_lifecycle_through_api(admin: ApiClient, app: FastAPI) -> None:
    driver_code = await _fleet(admin)
    recipient_id = (await admin.get("/api/v1/notification-recipients")).json()["data"][0]["id"]
    created = await admin.post("/api/v1/trips", json=_trip_body(driver_code, recipient_id))
    assert created.status_code == 201, created.text
    trip = created.json()["data"]
    assert trip["status"] == "configured" and trip["progress"] == 0
    assert trip["monitoringConfig"]["connectionLossSeconds"] == 300
    assert trip["recipients"][0]["telegramChatId"] == "-1001234"
    code = trip["code"]

    assert trip["directDistanceM"] > 0  # solo origen y destino; no se propone ruta
    assert (await admin.get(f"/api/v1/trips/{code}/planned-route")).status_code == 404

    started = await admin.post(f"/api/v1/trips/{code}/start")
    assert started.status_code == 200 and started.json()["data"]["status"] == "ongoing"
    again = await admin.post(f"/api/v1/trips/{code}/start")
    assert again.status_code == 409 and again.json()["error"]["code"] == "trip_already_started"

    vehicles = (await admin.get("/api/v1/vehicles")).json()["data"]
    assert vehicles[0]["status"] == "onRoute" and vehicles[0]["currentTrip"] == code
    assert vehicles[0]["currentDriver"] == "Luis Ramos"

    track = (await admin.get(f"/api/v1/trips/{code}/track")).json()["data"]
    assert track["type"] == "Feature" and track["properties"]["pointCount"] == 0

    patched = await admin.patch(f"/api/v1/trips/{code}/monitoring-config", json={"stopDurationSeconds": 600})
    assert patched.status_code == 200 and patched.json()["data"]["monitoringConfig"]["stopDurationSeconds"] == 600

    dashboard = (await admin.get("/api/v1/dashboard")).json()["data"]
    stats = {s["id"]: s["value"] for s in dashboard["stats"]}
    assert stats == {"active": 1, "trips": 1, "alerts": 0, "offline": 1}
    assert dashboard["vehicles"][0]["status"] == "Sin conexión"  # todavía no llegó telemetría

    # Llega una detección de CEP (como si viniera por events/detected)
    resources: AppResources = app.state.resources
    trip_id = uuid.UUID(started.json()["data"]["id"])
    now = datetime.now(UTC)
    async with open_scope(resources) as scope:
        await monitoring_factory.register_detected_event(scope).execute(
            DetectedEventCommand(
                event_id=uuid.uuid4(),
                event_type="ROUTE_DEVIATION",
                trip_id=trip_id,
                event_time=now,
                detected_at=now + timedelta(milliseconds=300),
                started_at=now - timedelta(minutes=2),
                latitude=-12.3,
                longitude=-76.8,
                evidence_from_sequence=None,
                evidence_to_sequence=None,
                metric_value=520.0,
            )
        )

    events = (await admin.get(f"/api/v1/events?trip_code={code}")).json()["data"]
    assert len(events) == 1
    event = events[0]
    assert event["type"] == "ROUTE_DEVIATION" and event["status"] == "pending" and event["severity"] == "HIGH"
    assert event["tripCode"] == code and event["vehicleCode"] == "TRK-003" and "520 m" in event["description"]
    assert "alejando del destino" in event["description"]
    reviewed = await admin.patch(f"/api/v1/events/{event['id']}/review")
    assert reviewed.status_code == 200 and reviewed.json()["data"]["status"] == "reviewed"
    assert (await admin.patch(f"/api/v1/events/{event['id']}/review")).status_code == 409

    finished = await admin.post(f"/api/v1/trips/{code}/finish")
    assert finished.json()["data"]["status"] == "completed" and finished.json()["data"]["progress"] == 100
    assert (await admin.post(f"/api/v1/trips/{code}/cancel")).status_code == 409
    vehicles = (await admin.get("/api/v1/vehicles")).json()["data"]
    assert vehicles[0]["status"] == "available"


async def test_trip_requires_recipients_and_gateway(admin: ApiClient) -> None:
    driver_code = await _fleet(admin)
    no_recipients = await admin.post(
        "/api/v1/trips", json={**_trip_body(driver_code, str(uuid.uuid4())), "recipientIds": []}
    )
    assert no_recipients.status_code == 422
    unknown_recipient = await admin.post("/api/v1/trips", json=_trip_body(driver_code, str(uuid.uuid4())))
    assert unknown_recipient.status_code == 422
    assert unknown_recipient.json()["error"]["code"] == "invalid_trip"


async def test_settings_roundtrip_preserves_extra_monitoring_fields(admin: ApiClient) -> None:
    settings = (await admin.get("/api/v1/settings")).json()["data"]
    assert settings["general"]["timezone"] == "America/Lima"
    assert "routeDeviationCorridorM" not in settings["monitoring"]  # sin ruta, sin corredor
    assert settings["monitoring"]["routeDeviationMinIncreaseM"] == 300
    settings["general"]["organizationName"] = "Transportes Andinos"
    settings["general"]["telegramEnabled"] = False
    settings["monitoring"]["stopDurationSeconds"] = 1200
    updated = await admin.put("/api/v1/settings", json=settings)
    assert updated.status_code == 200
    data = updated.json()["data"]
    assert data["general"]["organizationName"] == "Transportes Andinos"
    assert data["monitoring"]["stopDurationSeconds"] == 1200
    settings["monitoring"]["connectionLossSeconds"] = 1
    assert (await admin.put("/api/v1/settings", json=settings)).status_code == 422


async def test_integration_health_reports_real_status(admin: ApiClient) -> None:
    items = {i["key"]: i for i in (await admin.get("/api/v1/integration-health")).json()["data"]}
    assert items["database"]["status"] == "online"
    assert "mapbox" not in items  # la búsqueda de direcciones usa OpenStreetMap
    assert items["telegram"]["status"] == "unconfigured"
    assert items["cep"]["status"] in {"online", "offline"}


async def test_recipient_soft_delete(admin: ApiClient) -> None:
    created = await admin.post("/api/v1/notification-recipients", json={"name": "Ana", "telegramChatId": "55"})
    rid = created.json()["data"]["id"]
    assert (await admin.delete(f"/api/v1/notification-recipients/{rid}")).status_code == 204
    assert (await admin.get("/api/v1/notification-recipients")).json()["data"] == []
    assert (await admin.delete(f"/api/v1/notification-recipients/{rid}")).status_code == 404


async def test_openapi_documents_contract(client: ApiClient) -> None:
    spec = (await client.get("/api/v1/openapi.json")).json()
    assert "/api/v1/trips/{code}/start" in spec["paths"]
    assert "401" in spec["paths"]["/api/v1/trips"]["get"]["responses"]
