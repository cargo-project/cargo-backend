"""Nombres de los canales asíncronos que conectan los procesos de CarGO.

Son parte del contrato de integración, no de una tecnología en particular.
"""

from __future__ import annotations

from typing import Final

# --- broker IoT (frontera externa)
TELEMETRY_RAW_PREFIX: Final = "telemetry/raw"
TELEMETRY_RAW_SUBSCRIPTION: Final = "telemetry/raw/+"
DEVICE_TRIP_ASSIGNMENT: Final = "devices/{device_code}/trip"

# --- broker interno (red privada)
TELEMETRY_NORMALIZED: Final = "telemetry/normalized"
TELEMETRY_ENRICHED: Final = "telemetry/enriched"
EVENTS_DETECTED: Final = "events/detected"
TRIP_STARTED: Final = "trip/started"
TRIP_CONFIG_UPDATED: Final = "trip/config-updated"
TRIP_ENDED: Final = "trip/ended"


def device_trip_assignment_topic(device_code: str) -> str:
    return DEVICE_TRIP_ASSIGNMENT.format(device_code=device_code)


def device_code_from_raw_topic(topic: str) -> str | None:
    prefix = TELEMETRY_RAW_PREFIX + "/"
    if not topic.startswith(prefix):
        return None
    code = topic[len(prefix) :]
    return code if code and "/" not in code else None
