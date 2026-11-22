"""Lleva la lista de clientes WebSocket conectados y les manda avisos de cambio."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("cargo.websocket")


class ConnectionManager:
    """Los mensajes solo llevan ids ({type, tripId, vehicleId, eventId}); el cliente vuelve
    a pedir los datos por REST, así la autorización se queda en REST.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        return len(self._connections)

    async def register(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.add(websocket)
        logger.info("websocket connected", extra={"clients": self.count})

    async def unregister(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
        logger.info("websocket disconnected", extra={"clients": self.count})

    async def broadcast(self, message: dict[str, Any]) -> None:
        text = json.dumps(message, default=str)
        async with self._lock:
            targets = list(self._connections)
        failed: list[WebSocket] = []
        for websocket in targets:
            try:
                await asyncio.wait_for(websocket.send_text(text), timeout=5)
            except Exception as error:
                logger.warning("websocket send failed", extra={"error": type(error).__name__})
                failed.append(websocket)
        for websocket in failed:
            await self.unregister(websocket)
