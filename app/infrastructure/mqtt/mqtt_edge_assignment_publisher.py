"""EdgeAssignmentPublisher: mensaje retenido en devices/{code}/trip (broker IoT)."""

from __future__ import annotations

from typing import Any

from app.infrastructure.mqtt.mqtt_event_publisher import MqttEventPublisher
from app.shared.application.integration_topics import device_trip_assignment_topic


class MqttEdgeAssignmentPublisher:
    def __init__(self, iot_publisher: MqttEventPublisher) -> None:
        self._iot_publisher = iot_publisher

    async def publish(self, device_code: str, assignment: dict[str, Any]) -> None:
        # Retenido: si el dispositivo se (re)conecta después, igual recibe su viaje actual.
        await self._iot_publisher.publish_json(device_trip_assignment_topic(device_code), assignment, retain=True)
