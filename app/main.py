"""Armado de FastAPI: app, middlewares, ciclo de vida, routers, manejo de errores y docs."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.composition.resources import AppResources
from app.core.background.api_background_workers import ApiBackgroundWorkers
from app.core.config.settings import Settings, get_settings
from app.core.health.health_router import health_router
from app.core.http.error_handlers import register_error_handlers
from app.core.logging.logging_config import configure_logging
from app.core.realtime.connection_manager import ConnectionManager
from app.core.security.http_security_middleware import CSRF_HEADER, HttpSecurityMiddleware
from app.modules.administration.presentation.admin_router import admin_router
from app.modules.configuration.presentation.settings_router import settings_router
from app.modules.fleet.presentation.api.fleet_routers import (
    devices_router,
    drivers_router,
    vehicles_router,
)
from app.modules.identity.presentation.api.auth_router import auth_router
from app.modules.identity.presentation.api.users_router import users_router
from app.modules.monitoring.presentation.api.monitoring_routers import monitoring_router
from app.modules.monitoring.presentation.api.realtime_router import realtime_router
from app.modules.notifications.presentation.api.recipients_router import notifications_router
from app.modules.trips.presentation.api.trip_routers import (
    clients_router,
    geocoding_router,
    geofences_router,
    trips_router,
)

logger = logging.getLogger("cargo.api")

API_ROUTERS = (
    auth_router,
    users_router,
    admin_router,
    vehicles_router,
    drivers_router,
    devices_router,
    trips_router,
    clients_router,
    geofences_router,
    geocoding_router,
    monitoring_router,
    notifications_router,
    settings_router,
    realtime_router,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resources = AppResources.build(settings)
        connections = ConnectionManager()
        app.state.resources = resources
        app.state.connection_manager = connections
        workers: ApiBackgroundWorkers | None = None
        if settings.run_background_workers:
            workers = ApiBackgroundWorkers(resources, connections)
            workers.start()
            app.state.realtime_subscription = workers.subscription_state
        logger.info("api started", extra={"environment": settings.environment})
        try:
            yield
        finally:
            if workers is not None:
                await workers.stop()
            await resources.aclose()
            logger.info("api stopped")

    app = FastAPI(
        title="CarGO API",
        version="2.0.0",
        description=(
            "Backend of CarGO: automated real-time monitoring of heavy cargo vehicles. "
            "Authentication uses HttpOnly cookies; state-changing requests must send the "
            f"`{CSRF_HEADER}` header with the value of the `cargo_csrf` cookie. Successful "
            "responses are wrapped in `{data}` and errors in `{error}`."
        ),
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(HttpSecurityMiddleware, api_prefix=settings.api_prefix)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", CSRF_HEADER, "X-Request-ID"],
    )
    register_error_handlers(app)
    for router in API_ROUTERS:
        app.include_router(router, prefix=settings.api_prefix)
    app.include_router(health_router)
    return app


app = create_app()
