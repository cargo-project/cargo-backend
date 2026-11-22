from __future__ import annotations

from html import escape
from zoneinfo import ZoneInfo

from app.modules.notifications.application.dto.notification_dto import EventNotificationRequest

# (título, emoji) por tipo de evento: el emoji del encabezado identifica la alerta de un vistazo.
_TITLES: dict[str, tuple[str, str]] = {
    "TRIP_STARTED": ("Viaje iniciado", "🟢"),
    "ROUTE_DEVIATION": ("Posible desviación", "🧭"),
    "PROLONGED_STOP": ("Detención prolongada", "🛑"),
    "CONNECTION_LOSS": ("Pérdida de comunicación", "📡"),
    "DESTINATION_ARRIVAL": ("Llegada al destino", "🏁"),
    "EMERGENCY": ("Emergencia", "🚨"),
}
_SEVERITIES: dict[str, str] = {"CRITICAL": "Crítica", "HIGH": "Alta", "MEDIUM": "Media", "INFO": "Baja"}


def _field(label: str, value: str, emoji: str = "") -> str:
    prefix = f"{emoji} " if emoji else ""
    return f"{prefix}<b>{label}:</b> {escape(value)}"


class NotificationMessageComposer:
    """Mensaje de Telegram en HTML (el adaptador lo manda con parse_mode="HTML"): encabezado con
    el emoji del tipo de alerta y un dato por línea.

    Todo valor dinámico (códigos, nombres, descripción) pasa por html.escape, así lo que
    escriben los usuarios no puede romper el formato ni meter links. Fecha y hora van en la
    zona horaria configurada (Perú por defecto).
    """

    def __init__(self, timezone: str = "America/Lima") -> None:
        self._zone = ZoneInfo(timezone)

    def compose(self, request: EventNotificationRequest) -> str:
        title, emoji = _TITLES.get(request.event_type, (request.event_type, "🔔"))
        # Algo que pasó mientras no había señal: la fecha y hora son las de cuando ocurrió y
        # se agrega cuándo se detectó (al reconectar), para que no se confunda con algo actual.
        during_outage = request.delayed and request.event_type != "EMERGENCY"
        if during_outage:
            title = f"{title} (durante desconexión)"
        when = request.occurred_at if during_outage and request.occurred_at else request.detected_at
        local = when.astimezone(self._zone)
        lines = [f"{emoji} <b>CarGO | {escape(title)}</b>", ""]
        lines.append(_field("Viaje", request.trip_code))
        lines.append(_field("Vehículo", request.vehicle_code, "🚚"))
        if request.driver_name:
            lines.append(_field("Conductor", request.driver_name))
        lines += [
            _field("Detalle", request.description),
            _field("Severidad", _SEVERITIES.get(request.severity, request.severity)),
            _field("Fecha", f"{local:%d/%m/%Y}"),
            _field("Hora", f"{local:%H:%M:%S}"),
        ]
        if during_outage:
            detected = request.detected_at.astimezone(self._zone)
            lines.append(_field("Detectada al reconectar", f"{detected:%d/%m/%Y %H:%M:%S}"))
        if request.latitude is not None and request.longitude is not None:
            label = "Última ubicación conocida" if request.event_type == "CONNECTION_LOSS" else "Ubicación"
            url = f"https://maps.google.com/?q={request.latitude:.6f},{request.longitude:.6f}"
            lines.append(f'📍 <b>{label}:</b> <a href="{escape(url, quote=True)}">Ver en Google Maps</a>')
        return "\n".join(lines)
