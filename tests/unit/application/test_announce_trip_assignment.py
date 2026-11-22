from __future__ import annotations

import uuid
from typing import Any

from app.modules.monitoring.application.use_cases.announce_trip_assignment import (
    AnnounceTripAssignmentUseCase,
    TripLifecycleNotice,
)

DEVICE = uuid.uuid4()


class Directory:
    async def code_of(self, device_id: uuid.UUID) -> str | None:
        return "DEV-GW-003" if device_id == DEVICE else None


class Publisher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, device_code: str, assignment: dict[str, Any]) -> None:
        self.sent.append((device_code, assignment))


def _notice(active: bool, device: uuid.UUID | None = DEVICE) -> TripLifecycleNotice:
    details = {
        "origin_latitude": -12.0,
        "origin_longitude": -77.0,
        "destination_latitude": -12.1,
        "destination_longitude": -77.1,
    }
    return TripLifecycleNotice(trip_id="t-1", trip_code="TRP-1", device_id=device, active=active, details=details)


async def test_started_trip_is_announced_with_route_endpoints() -> None:
    publisher = Publisher()
    assert await AnnounceTripAssignmentUseCase(Directory(), publisher).execute(_notice(True))
    code, assignment = publisher.sent[0]
    assert code == "DEV-GW-003"
    assert assignment["active"] is True and assignment["destination_latitude"] == -12.1


async def test_ended_trip_is_announced_inactive_without_coordinates() -> None:
    publisher = Publisher()
    await AnnounceTripAssignmentUseCase(Directory(), publisher).execute(_notice(False))
    assert publisher.sent[0][1] == {"trip_id": "t-1", "trip_code": "TRP-1", "active": False}


async def test_unknown_or_missing_device_is_ignored() -> None:
    publisher = Publisher()
    use_case = AnnounceTripAssignmentUseCase(Directory(), publisher)
    assert not await use_case.execute(_notice(True, uuid.uuid4()))
    assert not await use_case.execute(_notice(True, None))
    assert publisher.sent == []
