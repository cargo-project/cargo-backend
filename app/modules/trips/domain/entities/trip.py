from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.modules.trips.domain.exceptions.trip_errors import (
    InvalidTripError,
    InvalidTripStateError,
    TripAlreadyFinishedError,
    TripAlreadyStartedError,
    TripNotStartedError,
)
from app.modules.trips.domain.value_objects.location import Location
from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration
from app.modules.trips.domain.value_objects.trip_status import TripStatus
from app.shared.domain.entity import Entity

MIN_ORIGIN_DESTINATION_DISTANCE_M = 100.0


@dataclass(eq=False)
class Trip(Entity):
    """Raíz de agregado del contexto de viajes.

    Invariantes que se cuidan acá (y en ningún otro lado):
      * el estado solo cambia con start/finish/cancel;
      * no se puede iniciar dos veces, terminar sin haber iniciado ni cambiar un viaje terminado;
      * origen y destino tienen que ser distintos;
      * hay al menos un destinatario de notificaciones;
      * la configuración de monitoreo es válida (la valida su value object).

    Un viaje es solo origen y destino: CarGO nunca propone ni guarda rutas. Lo que se
    ve en el mapa es la telemetría que mandó el vehículo.

    La telemetría y los eventos NO son parte del agregado: un viaje puede generar
    decenas de miles de lecturas, que se referencian por trip_id.
    """

    id: uuid.UUID
    code: str
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    origin: Location
    destination: Location
    cargo_description: str
    monitoring_configuration: MonitoringConfiguration
    recipient_ids: frozenset[uuid.UUID]
    status: TripStatus
    created_at: datetime
    created_by: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    planned_start_at: datetime | None = None
    device_id: uuid.UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    end_reason: str | None = None

    @classmethod
    def plan(
        cls,
        *,
        code: str,
        vehicle_id: uuid.UUID,
        driver_id: uuid.UUID,
        origin: Location,
        destination: Location,
        cargo_description: str,
        monitoring_configuration: MonitoringConfiguration,
        recipient_ids: frozenset[uuid.UUID],
        now: datetime,
        created_by: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
        planned_start_at: datetime | None = None,
    ) -> Trip:
        if origin.point.approximate_distance_m(destination.point) < MIN_ORIGIN_DESTINATION_DISTANCE_M:
            raise InvalidTripError("El origen y el destino deben ser lugares distintos.")
        cargo = " ".join(cargo_description.split())
        if not 3 <= len(cargo) <= 500:
            raise InvalidTripError("La descripción de la carga debe tener entre 3 y 500 caracteres.")
        if not recipient_ids:
            raise InvalidTripError("Selecciona al menos un destinatario de notificaciones.")
        if planned_start_at is not None and planned_start_at.tzinfo is None:
            raise InvalidTripError("La fecha planificada debe incluir zona horaria.")
        return cls(
            id=uuid.uuid4(),
            code=code,
            vehicle_id=vehicle_id,
            driver_id=driver_id,
            origin=origin,
            destination=destination,
            cargo_description=cargo,
            monitoring_configuration=monitoring_configuration,
            recipient_ids=frozenset(recipient_ids),
            status=TripStatus.CONFIGURED,
            created_at=now,
            created_by=created_by,
            client_id=client_id,
            planned_start_at=planned_start_at,
        )

    # ------------------------------------------------------------------ ciclo de vida
    def ensure_can_start(self) -> None:
        if self.status == TripStatus.ONGOING:
            raise TripAlreadyStartedError(f"El viaje {self.code} ya fue iniciado.")
        self._ensure_not_terminal()

    def start(self, *, now: datetime, device_id: uuid.UUID) -> None:
        self.ensure_can_start()
        self._transition(TripStatus.ONGOING)
        self.device_id = device_id
        self.started_at = now

    def finish(self, *, now: datetime, reason: str = "manual") -> None:
        if self.status == TripStatus.CONFIGURED:
            raise TripNotStartedError(f"El viaje {self.code} no puede finalizar sin haber iniciado.")
        self._ensure_not_terminal()
        self._transition(TripStatus.COMPLETED)
        self.completed_at = now
        self.end_reason = reason

    def cancel(self, *, now: datetime, reason: str = "cancelled_by_operator") -> None:
        self._ensure_not_terminal()
        self._transition(TripStatus.CANCELLED)
        self.cancelled_at = now
        self.end_reason = reason

    def update_monitoring_configuration(self, configuration: MonitoringConfiguration) -> None:
        self._ensure_not_terminal()
        self.monitoring_configuration = configuration

    # ------------------------------------------------------------------ consultas
    @property
    def is_monitored(self) -> bool:
        """CEP solo evalúa los viajes en curso."""
        return self.status == TripStatus.ONGOING

    @property
    def ended_at(self) -> datetime | None:
        return self.completed_at or self.cancelled_at

    # ------------------------------------------------------------------ internos
    def _ensure_not_terminal(self) -> None:
        if self.status.is_terminal:
            raise TripAlreadyFinishedError(f"El viaje {self.code} ya terminó ({self.status.value}); no admite cambios.")

    def _transition(self, target: TripStatus) -> None:
        if not self.status.can_transition_to(target):
            raise InvalidTripStateError(
                f"Transición no permitida: {self.status.value} → {target.value}.",
                details={"from": self.status.value, "to": target.value},
            )
        self.status = target
