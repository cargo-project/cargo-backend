"""Raíz de composición: recursos que se crean una sola vez por proceso a partir de la config.

Acá, y solo acá, se decide qué adaptador concreto implementa cada puerto.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config.settings import Settings

# Ojo: cada proceso (API y servicios del pipeline) tiene que registrar TODOS los modelos ORM,
# porque las FK entre módulos (ej. telemetry_events -> trips) se resuelven al hacer flush.
from app.infrastructure.database import model_registry  # noqa: F401
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.mapbox.mapbox_geocoding_provider import MapboxGeocodingProvider
from app.infrastructure.messaging.outbox_signal import OutboxSignal
from app.infrastructure.openstreetmap.photon_geocoding_provider import PhotonGeocodingProvider
from app.infrastructure.telegram.telegram_notification_adapter import TelegramNotificationAdapter
from app.modules.identity.infrastructure.security.argon2_password_hasher import (
    Argon2PasswordHasher,
)
from app.modules.identity.infrastructure.security.jwt_token_provider import JwtTokenProvider
from app.modules.notifications.application.ports.notification_gateway import NotificationGateway
from app.modules.trips.application.ports.geocoding_provider import GeocodingProvider
from app.shared.application.clock import Clock, SystemClock
from app.shared.domain.geo_point import GeoPoint


@dataclass
class AppResources:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    clock: Clock
    outbox_signal: OutboxSignal
    password_hasher: Argon2PasswordHasher
    token_provider: JwtTokenProvider
    http_client: httpx.AsyncClient
    geocoding_provider: GeocodingProvider
    notification_gateway: NotificationGateway

    @classmethod
    def build(cls, settings: Settings) -> AppResources:
        engine = create_engine(settings)
        http_client = httpx.AsyncClient(timeout=settings.http_timeout_seconds)
        mapbox_token = settings.mapbox_token.get_secret_value() if settings.mapbox_token else None
        geocoding_provider: GeocodingProvider
        if settings.geocoding_provider == "photon":
            bias = (
                GeoPoint(settings.geocoding_bias_latitude, settings.geocoding_bias_longitude)
                if settings.geocoding_bias_latitude is not None and settings.geocoding_bias_longitude is not None
                else None
            )
            geocoding_provider = PhotonGeocodingProvider(
                http_client, settings.photon_base_url, settings.external_user_agent, bias
            )
        else:
            geocoding_provider = MapboxGeocodingProvider(http_client, mapbox_token, settings.mapbox_api_base)
        telegram_token = settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else None
        return cls(
            settings=settings,
            engine=engine,
            session_factory=create_session_factory(engine),
            clock=SystemClock(),
            outbox_signal=OutboxSignal(),
            password_hasher=Argon2PasswordHasher(),
            token_provider=JwtTokenProvider(
                secret=settings.jwt_secret.get_secret_value(),
                algorithm=settings.jwt_algorithm,
                issuer=settings.jwt_issuer,
                access_ttl=timedelta(seconds=settings.access_token_ttl_seconds),
            ),
            http_client=http_client,
            geocoding_provider=geocoding_provider,
            notification_gateway=TelegramNotificationAdapter(http_client, telegram_token, settings.telegram_api_base),
        )

    async def aclose(self) -> None:
        await self.http_client.aclose()
        await self.engine.dispose()
