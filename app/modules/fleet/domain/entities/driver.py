from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.modules.fleet.domain.exceptions.fleet_errors import (
    DriverNotAvailableError,
    InvalidFleetStatusChangeError,
)
from app.modules.fleet.domain.services.field_rules import (
    normalise_code,
    normalise_identity_document,
    normalise_license,
    normalise_mobile_phone,
    require_text,
)
from app.shared.domain.entity import Entity


class DriverStatus(StrEnum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    INACTIVE = "inactive"


@dataclass(eq=False)
class Driver(Entity):
    """Raíz de agregado. ASSIGNED solo lo pone el ciclo de vida del viaje."""

    id: uuid.UUID
    code: str
    first_name: str
    last_name: str
    document_number: str
    license_number: str
    phone: str
    status: DriverStatus
    created_at: datetime

    @classmethod
    def register(
        cls,
        *,
        code: str,
        first_name: str,
        last_name: str,
        document_number: str,
        license_number: str,
        phone: str,
        status: DriverStatus,
        now: datetime,
    ) -> Driver:
        if status == DriverStatus.ASSIGNED:
            raise InvalidFleetStatusChangeError("Un conductor nuevo no puede registrarse como asignado.")
        driver = cls(
            id=uuid.uuid4(),
            code=normalise_code(code, label="conductor"),
            first_name="",
            last_name="",
            document_number="",
            license_number="",
            phone="",
            status=status,
            created_at=now,
        )
        driver.update_details(
            first_name=first_name,
            last_name=last_name,
            document_number=document_number,
            license_number=license_number,
            phone=phone,
        )
        return driver

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def update_details(
        self, *, first_name: str, last_name: str, document_number: str, license_number: str, phone: str
    ) -> None:
        self.first_name = require_text(first_name, label="nombre", max_length=60)
        self.last_name = require_text(last_name, label="apellido", max_length=60)
        self.document_number = normalise_identity_document(document_number)
        self.license_number = normalise_license(license_number)
        self.phone = normalise_mobile_phone(phone)

    def change_status(self, new_status: DriverStatus) -> None:
        if new_status == self.status:
            return
        if self.status == DriverStatus.ASSIGNED:
            raise InvalidFleetStatusChangeError(
                "El conductor está asignado a un viaje en curso; no se puede cambiar su estado."
            )
        if new_status == DriverStatus.ASSIGNED:
            raise InvalidFleetStatusChangeError("La asignación de un conductor la realiza el viaje.")
        self.status = new_status

    def ensure_available_for_trip(self) -> None:
        if self.status != DriverStatus.AVAILABLE:
            raise DriverNotAvailableError(
                f"El conductor {self.code} no está disponible (estado: {self.status.value}).",
                details={"driver": self.code, "status": self.status.value},
            )

    def assign_to_trip(self) -> None:
        self.ensure_available_for_trip()
        self.status = DriverStatus.ASSIGNED

    def release_from_trip(self) -> None:
        if self.status == DriverStatus.ASSIGNED:
            self.status = DriverStatus.AVAILABLE
