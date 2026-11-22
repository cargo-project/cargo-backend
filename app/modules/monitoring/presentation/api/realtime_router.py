"""Endpoint WebSocket (/api/v1/ws): el servidor empuja las novedades del monitoreo."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.composition import identity_factory
from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.core.realtime.connection_manager import ConnectionManager
from app.core.security.http_security_middleware import ACCESS_COOKIE, REFRESH_COOKIE
from app.shared.application.errors import AuthenticationError

logger = logging.getLogger("cargo.websocket")

realtime_router = APIRouter(tags=["realtime"])


async def _authenticate(websocket: WebSocket, resources: AppResources) -> bool:
    """Autenticación por cookies (la misma sesión que REST).

    Si el access token venció se valida la sesión de refresh, así un cliente que se
    reconecta después de un corte no queda afuera hasta su próxima llamada REST.
    """
    access = websocket.cookies.get(ACCESS_COOKIE)
    async with open_scope(resources) as scope:
        if access:
            try:
                claims = resources.token_provider.decode_access_token(access)
                user = await identity_factory.get_current_user(scope).execute(claims.user_id)
                return user.is_active
            except Exception:
                logger.debug("websocket access token rejected; trying refresh session")
        try:
            await identity_factory.validate_refresh_session(scope).execute(websocket.cookies.get(REFRESH_COOKIE))
            return True
        except AuthenticationError:
            return False


@realtime_router.websocket("/ws")
async def realtime(websocket: WebSocket) -> None:
    resources: AppResources = websocket.app.state.resources
    manager: ConnectionManager = websocket.app.state.connection_manager
    origin = websocket.headers.get("origin")
    if origin and origin not in resources.settings.cors_origins:
        logger.warning("websocket origin rejected", extra={"origin": origin})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    if not await _authenticate(websocket, resources):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await manager.register(websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    finally:
        await manager.unregister(websocket)
