from __future__ import annotations

from typing import Any


class MonitoringEventDescriber:
    """Arma la explicación en español de un evento detectado a partir de su evidencia."""

    def describe(self, event_type: str, details: dict[str, Any]) -> str:
        text = self._describe(event_type, details)
        if details.get("delayed") and event_type in ("ROUTE_DEVIATION", "PROLONGED_STOP"):
            text += " Ocurrió mientras no había señal y se detectó al reconectar."
        return text

    def _describe(self, event_type: str, details: dict[str, Any]) -> str:
        metric = details.get("metric_value")
        duration = details.get("duration_seconds")
        delayed = " (recibida con retraso)" if details.get("delayed") else ""
        if event_type == "ROUTE_DEVIATION":
            text = "El vehículo se está alejando del destino"
            if metric is not None:
                text += f": {float(metric):.0f} m más lejos que el punto más cercano que había alcanzado"
            if duration:
                text += f", durante {int(duration)} s"
            return text + "."
        if event_type == "PROLONGED_STOP":
            minutes = int(duration // 60) if duration else None
            return f"Detención prolongada{f' de {minutes} min' if minutes else ''} fuera de lo previsto."
        if event_type == "CONNECTION_LOSS":
            seconds = int(metric) if metric is not None else None
            return f"Sin telemetría en tiempo real{f' durante {seconds} s' if seconds else ''}."
        if event_type == "DESTINATION_ARRIVAL":
            return "El vehículo llegó y permaneció en la zona de destino."
        if event_type == "EMERGENCY":
            return f"El conductor activó el botón de emergencia{delayed}."
        if event_type == "TRIP_STARTED":
            origin, destination = details.get("origin_label"), details.get("destination_label")
            route = f": {origin} ➜ {destination}" if origin and destination else ""
            return f"Inició el viaje{route}. Monitoreo en tiempo real activo."
        return event_type
