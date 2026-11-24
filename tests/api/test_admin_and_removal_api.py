"""Eliminación de registros de flota y consola del administrador."""

from __future__ import annotations

import pytest

from tests.api.conftest import ApiClient
from tests.api.test_business_api import _fleet, _trip_body

pytestmark = pytest.mark.integration


async def test_unused_fleet_records_can_be_deleted(admin: ApiClient) -> None:
    await _fleet(admin)
    driver_code = (await admin.get("/api/v1/drivers")).json()["data"][0]["code"]

    assert (await admin.delete("/api/v1/devices/DEV-GW-003")).status_code == 204
    assert (await admin.delete("/api/v1/vehicles/trk-003")).status_code == 204
    assert (await admin.delete(f"/api/v1/drivers/{driver_code}")).status_code == 204

    assert (await admin.get("/api/v1/vehicles")).json()["data"] == []
    assert (await admin.get("/api/v1/devices")).json()["data"] == []
    assert (await admin.delete("/api/v1/vehicles/TRK-003")).status_code == 404

    activity = (await admin.get("/api/v1/admin/activity", params={"category": "fleet"})).json()["data"]
    actions = {entry["action"] for entry in activity}
    assert {"vehicle.deleted", "driver.deleted", "device.deleted"} <= actions


async def test_records_with_trips_are_kept(admin: ApiClient) -> None:
    driver_code = await _fleet(admin)
    recipient_id = (await admin.get("/api/v1/notification-recipients")).json()["data"][0]["id"]
    created = await admin.post("/api/v1/trips", json=_trip_body(driver_code, recipient_id))
    assert created.status_code == 201, created.text

    vehicle = await admin.delete("/api/v1/vehicles/TRK-003")
    assert vehicle.status_code == 409
    assert vehicle.json()["error"]["code"] == "fleet_resource_in_use"
    assert "viaje" in vehicle.json()["error"]["message"]
    assert (await admin.delete(f"/api/v1/drivers/{driver_code}")).status_code == 409
    assert (await admin.delete("/api/v1/devices/DEV-GW-003")).status_code == 409
    assert len((await admin.get("/api/v1/vehicles")).json()["data"]) == 1


async def test_operator_can_delete_unused_records(operator: ApiClient, admin: ApiClient) -> None:
    await _fleet(admin)
    assert (await operator.delete("/api/v1/devices/DEV-GW-003")).status_code == 204


async def test_admin_overview_and_activity(admin: ApiClient) -> None:
    await _fleet(admin)
    overview = await admin.get("/api/v1/admin/overview")
    assert overview.status_code == 200, overview.text
    data = overview.json()["data"]
    assert data["fleet"] == {
        "vehicles": 1,
        "drivers": 1,
        "devices": 1,
        "devicesOnline": 0,
        "activeTrips": 0,
        "totalTrips": 0,
    }
    assert data["loginsLastDay"] >= 1
    admin_account = next(a for a in data["accounts"] if a["role"] == "ADMIN")
    assert admin_account["lastLoginAt"] is not None

    logins = (await admin.get("/api/v1/admin/activity", params={"category": "auth"})).json()["data"]
    assert logins and all(entry["action"].startswith("user.") for entry in logins)
    assert (await admin.get("/api/v1/admin/activity", params={"category": "nope"})).status_code == 422
    assert (await admin.get("/api/v1/integration-health")).status_code == 200


async def test_admin_cannot_lock_themselves_out(admin: ApiClient) -> None:
    me = (await admin.get("/api/v1/auth/me")).json()["data"]
    demote = await admin.patch(f"/api/v1/users/{me['id']}", json={"role": "OPERATOR"})
    assert demote.status_code == 422
    assert demote.json()["error"]["code"] == "self_lockout"
    assert (await admin.patch(f"/api/v1/users/{me['id']}", json={"isActive": False})).status_code == 422
    assert (await admin.patch(f"/api/v1/users/{me['id']}", json={"fullName": "Admin Principal"})).status_code == 200
