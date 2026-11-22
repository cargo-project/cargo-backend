"""Puerto de límite de transacción.

Los casos de uso que cambian varios agregados (ej. iniciar un viaje reserva vehículo y
conductor y encola un evento) llaman a commit una sola vez, así el cambio es atómico.
Los de solo lectura no lo necesitan.
"""

from __future__ import annotations

from typing import Protocol


class UnitOfWork(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
