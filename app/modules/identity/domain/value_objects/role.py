from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Roles fijos. ADMIN maneja configuración y destinatarios; OPERATOR opera los viajes."""

    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
