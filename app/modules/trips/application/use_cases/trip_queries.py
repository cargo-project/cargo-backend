from __future__ import annotations

from app.modules.trips.application.dto.trip_dto import TripView
from app.modules.trips.application.ports.trip_read_model import TripReadModel
from app.modules.trips.domain.exceptions.trip_errors import TripNotFoundError


class ListTripsUseCase:
    def __init__(self, read_model: TripReadModel) -> None:
        self._read_model = read_model

    async def execute(self) -> list[TripView]:
        return await self._read_model.list_trips()


class GetTripUseCase:
    def __init__(self, read_model: TripReadModel) -> None:
        self._read_model = read_model

    async def execute(self, code: str) -> TripView:
        view = await self._read_model.get_trip(code.upper())
        if view is None:
            raise TripNotFoundError(f"No existe el viaje {code}.")
        return view
