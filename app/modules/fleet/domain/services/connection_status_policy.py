from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum


class ConnectionStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    INACTIVE = "inactive"


def derive_connection_status(
    *, is_active: bool, last_connection_at: datetime | None, now: datetime, online_window: timedelta
) -> ConnectionStatus:
    """Un dispositivo está online si mandó datos dentro de online_window.

    La usan IoTDevice y los read models que no cargan el agregado; así la regla
    está en un solo lugar.
    """
    if not is_active:
        return ConnectionStatus.INACTIVE
    if last_connection_at is not None and now - last_connection_at <= online_window:
        return ConnectionStatus.ONLINE
    return ConnectionStatus.OFFLINE
