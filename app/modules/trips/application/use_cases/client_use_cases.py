from __future__ import annotations

import uuid

from app.modules.trips.domain.entities.client import Client
from app.modules.trips.domain.repositories.trip_repositories import ClientRepository
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork


class ListClientsUseCase:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def execute(self) -> list[Client]:
        return await self._clients.list_all()


class CreateClientUseCase:
    def __init__(self, clients: ClientRepository, uow: UnitOfWork, clock: Clock, audit: AuditLog) -> None:
        self._clients = clients
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def execute(self, *, name: str, tax_id: str | None, contact_email: str | None, actor_id: uuid.UUID) -> Client:
        client = Client.register(name=name, tax_id=tax_id, contact_email=contact_email, now=self._clock.now())
        await self._clients.add(client)
        await self._audit.record(
            action="client.created", entity_type="client", entity_id=str(client.id), actor_id=actor_id
        )
        await self._uow.commit()
        return client
