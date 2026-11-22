"""Chequeos reales de conexión para Configuración -> Integraciones y para el readiness."""

from __future__ import annotations

import asyncio

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.telegram.telegram_notification_adapter import TelegramNotificationAdapter
from app.modules.configuration.application.ports import IntegrationStatus


class DatabaseProbe:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def check(self) -> IntegrationStatus:
        try:
            async with self._session_factory() as session:
                version = await asyncio.wait_for(session.scalar(text("SELECT postgis_version()")), 3)
            return IntegrationStatus("database", "PostgreSQL + PostGIS", "online", f"PostGIS {version}")
        except Exception as error:
            return IntegrationStatus("database", "PostgreSQL + PostGIS", "offline", type(error).__name__)


class TcpProbe:
    """Abre una conexión TCP; se usa para los brokers y para el runtime CEP."""

    def __init__(self, key: str, name: str, host: str, port: int) -> None:
        self._key, self._name, self._host, self._port = key, name, host, port

    async def check(self) -> IntegrationStatus:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(self._host, self._port), 2)
            writer.close()
            await writer.wait_closed()
            return IntegrationStatus(self._key, self._name, "online", f"{self._host}:{self._port} accesible")
        except (OSError, TimeoutError):
            return IntegrationStatus(self._key, self._name, "offline", f"{self._host}:{self._port} sin respuesta")


class TelegramProbe:
    def __init__(self, adapter: TelegramNotificationAdapter) -> None:
        self._adapter = adapter

    async def check(self) -> IntegrationStatus:
        if not self._adapter.is_configured:
            return IntegrationStatus("telegram", "Telegram Bot API", "unconfigured", "TELEGRAM_BOT_TOKEN vacío")
        ok, detail = await self._adapter.check()
        return IntegrationStatus("telegram", "Telegram Bot API", "online" if ok else "offline", detail)


class MapboxProbe:
    def __init__(self, client: httpx.AsyncClient, token: str | None, api_base: str) -> None:
        self._client = client
        self._token = token
        self._api_base = api_base.rstrip("/")

    async def check(self) -> IntegrationStatus:
        if not self._token:
            return IntegrationStatus("mapbox", "Mapbox", "unconfigured", "MAPBOX_TOKEN vacío")
        try:
            response = await self._client.get(f"{self._api_base}/tokens/v2", params={"access_token": self._token})
            valid = response.status_code == 200 and response.json().get("code") == "TokenValid"
            return IntegrationStatus(
                "mapbox",
                "Mapbox",
                "online" if valid else "offline",
                "Token válido" if valid else f"Token rechazado ({response.status_code})",
            )
        except (httpx.HTTPError, ValueError) as error:
            return IntegrationStatus("mapbox", "Mapbox", "offline", type(error).__name__)
