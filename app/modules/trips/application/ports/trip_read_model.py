from __future__ import annotations

from typing import Protocol

from app.modules.trips.application.dto.trip_dto import TripView


class TripReadModel(Protocol):
    """Lado de consulta para las pantallas de viajes (cruza vehículo, conductor, destinatarios y avance)."""

    async def list_trips(self) -> list[TripView]: ...

    async def get_trip(self, code: str) -> TripView | None: ...
