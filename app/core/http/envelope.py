"""Formato de respuesta común a todos los routers.

El frontend (services/apiClient.ts) espera {"data": T} cuando todo va bien
y {"error": {"code", "message", "details", "requestId"}} cuando falla.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base de los esquemas HTTP: snake_case en Python, camelCase hacia el frontend."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class DataEnvelope[T](BaseModel):
    data: T


class ErrorBody(CamelModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


def wrap[T](data: T) -> DataEnvelope[T]:
    return DataEnvelope[T](data=data)


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope, "description": "Not authenticated or session expired"},
    403: {"model": ErrorEnvelope, "description": "Forbidden (role or CSRF)"},
    404: {"model": ErrorEnvelope, "description": "Resource not found"},
    409: {"model": ErrorEnvelope, "description": "Conflict with current state"},
    422: {"model": ErrorEnvelope, "description": "Validation or business rule error"},
}
