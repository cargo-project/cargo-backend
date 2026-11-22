"""Parámetros de conexión y fábrica de clientes para los dos brokers MQTT."""

from __future__ import annotations

import ssl
from dataclasses import dataclass

import aiomqtt

from app.core.config.settings import Settings


@dataclass(frozen=True, slots=True)
class MqttEndpoint:
    name: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    tls: bool = False
    ca_file: str | None = None

    def create_client(self, client_id: str, *, clean_session: bool = False) -> aiomqtt.Client:
        tls_context: ssl.SSLContext | None = None
        if self.tls:
            tls_context = ssl.create_default_context(cafile=self.ca_file)
        return aiomqtt.Client(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            identifier=client_id,
            clean_session=clean_session,
            tls_context=tls_context,
            keepalive=30,
        )


def iot_endpoint(settings: Settings) -> MqttEndpoint:
    return MqttEndpoint(
        name="iot",
        host=settings.mqtt_iot_host,
        port=settings.mqtt_iot_port,
        username=settings.mqtt_iot_username,
        password=settings.mqtt_iot_password.get_secret_value() if settings.mqtt_iot_password else None,
        tls=settings.mqtt_iot_tls,
        ca_file=settings.mqtt_iot_ca_file,
    )


def internal_endpoint(settings: Settings) -> MqttEndpoint:
    password = settings.mqtt_internal_password
    return MqttEndpoint(
        name="internal",
        host=settings.mqtt_internal_host,
        port=settings.mqtt_internal_port,
        username=settings.mqtt_internal_username,
        password=password.get_secret_value() if password else None,
    )
