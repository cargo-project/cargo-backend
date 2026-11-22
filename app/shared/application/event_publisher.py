"""Puerto para publicar eventos de integración.

Los eventos de integración salen del contexto (los consumen otros procesos). El
adaptador real es el outbox transaccional, así publicar forma parte de la unit of work
del que llama y recién llega a MQTT después del commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class IntegrationEvent:
    topic: str
    payload: dict[str, Any]
    retain: bool = False


class EventPublisher(Protocol):
    async def publish(self, event: IntegrationEvent) -> None: ...
