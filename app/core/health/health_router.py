"""Endpoints de liveness/readiness para Docker y Nginx (no son parte de la API de negocio)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.composition.resources import AppResources
from app.infrastructure.health.integration_probes import DatabaseProbe

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/live", summary="Process is up and serving requests")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@health_router.get("/ready", summary="Dependencies required to serve traffic are reachable")
async def ready(request: Request) -> JSONResponse:
    resources: AppResources = request.app.state.resources
    database = await DatabaseProbe(resources.session_factory).check()
    checks: dict[str, Any] = {"database": database.status}
    state = getattr(request.app.state, "realtime_subscription", None)
    if state is not None:
        checks["mqtt_internal"] = "online" if state.connected else "offline"
    healthy = all(value == "online" for value in checks.values())
    body = {"status": "ready" if healthy else "degraded", "checks": checks}
    return JSONResponse(status_code=200 if healthy else 503, content=body)
