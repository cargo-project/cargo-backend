"""Loop de suscripción MQTT resistente a fallos; lo usan todos los procesos que consumen."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

import aiomqtt

from app.infrastructure.mqtt.mqtt_endpoint import MqttEndpoint

logger = logging.getLogger("cargo.mqtt.subscription")

MessageHandler = Callable[[str, bytes], Awaitable[None]]


@dataclass(slots=True)
class SubscriptionState:
    connected: bool = False


async def run_subscription(
    endpoint: MqttEndpoint,
    *,
    client_id: str,
    topics: Sequence[str],
    handler: MessageHandler,
    stop: asyncio.Event,
    state: SubscriptionState | None = None,
    reconnect_delay_seconds: float = 3.0,
) -> None:
    """Suscribe con QoS 1 y sesión persistente (clean_session=False).

    Con un client_id fijo el broker guarda los mensajes QoS 1 mientras el consumidor
    está abajo, así un reinicio no pierde telemetría. Si el handler lanza una excepción
    se loguea y el loop sigue: un mensaje malo no puede parar el pipeline.
    """
    state = state or SubscriptionState()
    while not stop.is_set():
        try:
            async with endpoint.create_client(client_id, clean_session=False) as client:
                for topic in topics:
                    await client.subscribe(topic, qos=1)
                state.connected = True
                logger.info(
                    "mqtt subscribed",
                    extra={"broker": endpoint.name, "client_id": client_id, "topics": list(topics)},
                )
                messages = aiter(client.messages)
                while not stop.is_set():
                    next_message = asyncio.ensure_future(anext(messages))
                    stopper = asyncio.ensure_future(stop.wait())
                    done, _ = await asyncio.wait({next_message, stopper}, return_when=asyncio.FIRST_COMPLETED)
                    if next_message not in done:
                        next_message.cancel()
                        break
                    stopper.cancel()
                    message = next_message.result()
                    payload = message.payload if isinstance(message.payload, bytes) else b""
                    try:
                        await handler(message.topic.value, payload)
                    except Exception:
                        logger.exception("mqtt handler failed", extra={"topic": message.topic.value})
        except aiomqtt.MqttError as error:
            state.connected = False
            logger.warning(
                "mqtt connection lost; reconnecting",
                extra={"broker": endpoint.name, "client_id": client_id, "error": str(error)},
            )
            try:
                await asyncio.wait_for(stop.wait(), reconnect_delay_seconds)
            except TimeoutError:
                continue
        finally:
            state.connected = False
