"""Adaptadores externos probados con transportes simulados (sin red)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from app.infrastructure.mapbox.mapbox_geocoding_provider import MapboxGeocodingProvider
from app.infrastructure.mqtt.message_parsers import (
    MAX_BATCH_EVENTS,
    InvalidMessageError,
    parse_detected_event,
    parse_detected_events,
    parse_raw_telemetry,
)
from app.infrastructure.telegram.telegram_notification_adapter import TelegramNotificationAdapter
from app.modules.notifications.domain.exceptions.notification_errors import NotificationDeliveryError
from app.shared.application.errors import ExternalServiceUnavailableError
from app.shared.application.integration_topics import device_code_from_raw_topic
from app.shared.domain.geo_point import GeoPoint

NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


async def test_telegram_success_and_payload() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    adapter = TelegramNotificationAdapter(_client(httpx.MockTransport(handle)), "123:ABC", "https://tg.test")
    await adapter.send("-1001", "hola")
    assert json.loads(seen[0].content) == {
        "chat_id": "-1001",
        "text": "hola",
        "parse_mode": "HTML",  # el compositor arma negritas y el link en HTML
        "disable_web_page_preview": True,
    }


@pytest.mark.parametrize(("status", "retryable"), [(429, True), (502, True), (400, False), (403, False)])
async def test_telegram_error_classification(status: int, retryable: bool) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json={"description": "nope"}))
    adapter = TelegramNotificationAdapter(_client(transport), "123:ABC", "https://tg.test")
    with pytest.raises(NotificationDeliveryError) as error:
        await adapter.send("1", "x")
    assert error.value.retryable is retryable
    assert "123:ABC" not in str(error.value)  # el token del bot nunca termina guardado en el error


async def test_telegram_timeout_is_retryable() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    adapter = TelegramNotificationAdapter(_client(httpx.MockTransport(handle)), "t", "https://tg.test")
    with pytest.raises(NotificationDeliveryError) as error:
        await adapter.send("1", "x")
    assert error.value.retryable


async def test_mapbox_without_token_is_unavailable() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    with pytest.raises(ExternalServiceUnavailableError):
        await MapboxGeocodingProvider(_client(transport), None, "https://m").search("lima", 5)


async def test_mapbox_reverse_geocoding() -> None:
    body = {
        "features": [
            {
                "geometry": {"coordinates": [-77.03, -12.05]},
                "properties": {"mapbox_id": "x1", "full_address": "Av. Arequipa 123, Lima", "feature_type": "address"},
            }
        ]
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    result = await MapboxGeocodingProvider(_client(transport), "pk", "https://m").reverse(GeoPoint(-12.05, -77.03))
    assert result.display_name == "Av. Arequipa 123, Lima"


def test_raw_telemetry_parser() -> None:
    payload = json.dumps(
        {
            "message_id": str(uuid.uuid4()),
            "device_id": "dev-gw-001",
            "trip_id": str(uuid.uuid4()),
            "sequence": 5,
            "event_time": "2026-11-09T11:59:00-05:00",
            "latitude": -12.0,
            "longitude": -77.0,
            "speed_kmh": 10.5,
        }
    ).encode()
    command = parse_raw_telemetry("DEV-GW-001", payload, NOW)
    assert command.device_code == "DEV-GW-001"
    assert command.event_time.tzinfo == UTC
    assert command.received_at == NOW


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"[]",
        json.dumps({"device_id": "X"}).encode(),
        b"{" + b"x" * 5000 + b"}",
        json.dumps(
            {
                "message_id": str(uuid.uuid4()),
                "device_id": "DEV-1",
                "trip_id": str(uuid.uuid4()),
                "sequence": 1,
                "event_time": "2026-11-09T12:00:00",
                "latitude": 1,
                "longitude": 1,
                "speed_kmh": 1,
            }
        ).encode(),
    ],  # marca de tiempo sin zona horaria
)
def test_raw_telemetry_parser_rejects_malformed(payload: bytes) -> None:
    with pytest.raises(InvalidMessageError):
        parse_raw_telemetry("DEV-1", payload, NOW)


def test_detected_event_parser_accepts_siddhi_envelope() -> None:
    event_id = uuid.uuid4()
    payload = json.dumps(
        {
            "event": {
                "event_id": str(event_id),
                "event_type": "CONNECTION_LOSS",
                "trip_id": str(uuid.uuid4()),
                "event_time_ms": 1_762_689_600_000,
                "detected_at_ms": 1_762_689_601_000,
                "started_at_ms": -1,
                "latitude": 0.0,
                "longitude": 0.0,
                "evidence_from_sequence": -1,
                "evidence_to_sequence": -1,
                "metric_value": 310.0,
                "delayed": False,
            }
        }
    ).encode()
    command = parse_detected_event(payload)
    assert command.event_id == event_id
    assert command.started_at is None
    assert command.evidence_from_sequence is None


def _siddhi_event(event_type: str = "CONNECTION_LOSS") -> dict[str, object]:
    return {
        "event": {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "trip_id": str(uuid.uuid4()),
            "event_time_ms": 1_762_689_600_000,
            "detected_at_ms": 1_762_689_601_000,
            "metric_value": 310.0,
        }
    }


def test_detected_events_parser_accepts_a_single_event_as_a_batch_of_one() -> None:
    event = _siddhi_event()
    batch = parse_detected_events(json.dumps(event).encode())
    assert [str(c.event_id) for c in batch.commands] == [event["event"]["event_id"]]  # type: ignore[index]
    assert batch.rejected == []


def test_detected_events_parser_accepts_siddhi_batches() -> None:
    # Siddhi manda una lista cuando varias detecciones salen en el mismo ciclo (p. ej. el trigger de 5 s).
    events = [_siddhi_event(), _siddhi_event(), _siddhi_event("PROLONGED_STOP")]
    batch = parse_detected_events(json.dumps(events).encode())
    assert [c.event_type for c in batch.commands] == ["CONNECTION_LOSS", "CONNECTION_LOSS", "PROLONGED_STOP"]
    assert len({c.event_id for c in batch.commands}) == 3


def test_detected_events_parser_keeps_valid_items_when_one_is_invalid() -> None:
    events = [_siddhi_event(), {"event": {"event_type": "CONNECTION_LOSS"}}, "basura", _siddhi_event()]
    batch = parse_detected_events(json.dumps(events).encode())
    assert len(batch.commands) == 2
    assert [reason.split(":")[0] for reason in batch.rejected] == ["item 1", "item 2"]


def test_detected_events_parser_limits_batches() -> None:
    too_many = [_siddhi_event() for _ in range(MAX_BATCH_EVENTS + 1)]
    with pytest.raises(InvalidMessageError, match="batch too large"):
        parse_detected_events(json.dumps(too_many).encode())
    # un objeto suelto sigue limitado a MAX_PAYLOAD_BYTES aunque el lote permita más
    with pytest.raises(InvalidMessageError, match="too large"):
        parse_detected_events(json.dumps({"event": {"pad": "x" * 5000}}).encode())
    with pytest.raises(InvalidMessageError):
        parse_detected_events(b"not json")


def test_trip_started_parser_builds_an_idempotent_alert() -> None:
    from app.infrastructure.mqtt.message_parsers import parse_trip_started

    trip_id = uuid.uuid4()
    started = {
        "trip_id": str(trip_id),
        "trip_code": "TRP-1",
        "occurred_at_ms": 1_762_700_000_000,
        "started_at_ms": 1_762_689_600_000,
        "origin_latitude": -12.05,
        "origin_longitude": -77.03,
        "origin_label": "Plaza San Martín",
        "destination_label": "Parque Kennedy",
    }
    first = parse_trip_started(json.dumps(started).encode())
    reannounced = parse_trip_started(json.dumps({**started, "occurred_at_ms": 1_762_700_060_000}).encode())
    assert first.event_type == "TRIP_STARTED"
    assert first.event_id == reannounced.event_id  # misma alerta, llegue trip/started las veces que llegue
    assert first.event_time == datetime.fromtimestamp(1_762_689_600, UTC)  # el inicio real, no el del reanuncio
    assert first.extra_details == {"origin_label": "Plaza San Martín", "destination_label": "Parque Kennedy"}


def test_raw_topic_device_extraction() -> None:
    assert device_code_from_raw_topic("telemetry/raw/DEV-GW-001") == "DEV-GW-001"
    assert device_code_from_raw_topic("telemetry/raw/a/b") is None
    assert device_code_from_raw_topic("other/DEV") is None
