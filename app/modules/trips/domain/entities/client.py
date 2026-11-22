from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.modules.trips.domain.exceptions.trip_errors import InvalidTripError
from app.shared.domain.entity import Entity


@dataclass(eq=False)
class Client(Entity):
    """Cliente o destinatario de la carga. En el viaje es opcional."""

    id: uuid.UUID
    name: str
    tax_id: str | None
    contact_email: str | None
    created_at: datetime

    @classmethod
    def register(cls, *, name: str, tax_id: str | None, contact_email: str | None, now: datetime) -> Client:
        cleaned = " ".join(name.split())
        if not 2 <= len(cleaned) <= 160:
            raise InvalidTripError("El nombre del cliente debe tener entre 2 y 160 caracteres.")
        return cls(
            id=uuid.uuid4(),
            name=cleaned,
            tax_id=(tax_id or "").strip() or None,
            contact_email=(contact_email or "").strip().lower() or None,
            created_at=now,
        )
