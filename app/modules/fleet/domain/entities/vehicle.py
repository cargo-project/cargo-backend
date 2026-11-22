from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.modules.fleet.domain.exceptions.fleet_errors import (
    InvalidFleetStatusChangeError,
    VehicleNotAvailableError,
)
from app.modules.fleet.domain.services.field_rules import normalise_code, require_text
from app.shared.domain.entity import Entity


class VehicleStatus(StrEnum):
    AVAILABLE = "available"
    ON_ROUTE = "on_route"
    STOPPED = "stopped"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


# Estados que el operador puede poner a mano. ON_ROUTE/STOPPED los maneja el viaje.
MANUAL_VEHICLE_STATUSES = frozenset({VehicleStatus.AVAILABLE, VehicleStatus.MAINTENANCE, VehicleStatus.OFFLINE})


@dataclass(eq=False)
class Vehicle(Entity):
    """Raíz de agregado. Su estado operativo está protegido: solo un viaje lo pone en ruta."""

    id: uuid.UUID
    code: str
    plate: str
    brand: str
    model: str
    description: str
    status: VehicleStatus
    created_at: datetime

    @classmethod
    def register(
        cls,
        *,
        code: str,
        plate: str,
        brand: str,
        model: str,
        description: str,
        status: VehicleStatus,
        now: datetime,
    ) -> Vehicle:
        if status not in MANUAL_VEHICLE_STATUSES:
            raise InvalidFleetStatusChangeError(
                "Un vehículo nuevo solo puede registrarse como disponible, en mantenimiento o sin conexión."
            )
        return cls(
            id=uuid.uuid4(),
            code=normalise_code(code, label="vehículo"),
            plate=require_text(plate, label="placa", min_length=3, max_length=16).upper(),
            brand=require_text(brand, label="marca", max_length=60),
            model=require_text(model, label="modelo", max_length=60),
            description=description.strip()[:500],
            status=status,
            created_at=now,
        )

    def update_details(self, *, plate: str, brand: str, model: str, description: str) -> None:
        self.plate = require_text(plate, label="placa", min_length=3, max_length=16).upper()
        self.brand = require_text(brand, label="marca", max_length=60)
        self.model = require_text(model, label="modelo", max_length=60)
        self.description = description.strip()[:500]

    def change_status(self, new_status: VehicleStatus) -> None:
        """Cambio de estado manual pedido por un operador."""
        if new_status == self.status:
            return
        if self.status == VehicleStatus.ON_ROUTE:
            raise InvalidFleetStatusChangeError("El vehículo está en ruta; su estado lo controla el viaje en curso.")
        if new_status not in MANUAL_VEHICLE_STATUSES:
            raise InvalidFleetStatusChangeError(
                "El estado 'en ruta' o 'detenido' solo lo asigna el ciclo de vida del viaje."
            )
        self.status = new_status

    def ensure_available_for_trip(self) -> None:
        if self.status != VehicleStatus.AVAILABLE:
            raise VehicleNotAvailableError(
                f"El vehículo {self.code} no está disponible (estado: {self.status.value}).",
                details={"vehicle": self.code, "status": self.status.value},
            )

    def depart_on_trip(self) -> None:
        self.ensure_available_for_trip()
        self.status = VehicleStatus.ON_ROUTE

    def return_from_trip(self) -> None:
        if self.status in (VehicleStatus.ON_ROUTE, VehicleStatus.STOPPED):
            self.status = VehicleStatus.AVAILABLE
