"""WebSocket: autenticación por cookie, chequeo de Origin y push del servidor."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config.settings import Settings
from app.main import create_app
from tests.support.database import truncate_all
from tests.support.seed import ADMIN_EMAIL, PASSWORD, seed_users

pytestmark = pytest.mark.integration


def test_websocket_push_requires_session_and_allowed_origin(settings: Settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        client.portal.call(truncate_all, app.state.resources.engine)
        client.portal.call(seed_users, app.state.resources)

        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/v1/ws") as ws:
            ws.receive_text()  # una conexión anónima se cierra con violación de política

        assert client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200

        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect("/api/v1/ws", headers={"origin": "https://evil.example"}) as ws,
        ):
            ws.receive_text()

        with client.websocket_connect("/api/v1/ws", headers={"origin": "http://localhost:3000"}) as ws:
            ws.send_text("ping")
            assert ws.receive_json() == {"type": "pong"}
            client.portal.call(
                app.state.connection_manager.broadcast,
                {"type": "monitoring.event_created", "tripId": "TRP-1", "vehicleId": "TRK-1"},
            )
            assert ws.receive_json() == {"type": "monitoring.event_created", "tripId": "TRP-1", "vehicleId": "TRK-1"}
