"""Convierte los errores semánticos en respuestas HTTP (único lugar que conoce los status codes)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.application.errors import (
    AuthenticationError,
    AuthorizationError,
    ExternalServiceUnavailableError,
)
from app.shared.domain.errors import (
    BusinessRuleViolationError,
    ConflictError,
    DomainError,
    EntityNotFoundError,
)

logger = logging.getLogger("cargo.http")

_STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (EntityNotFoundError, 404),
    (ConflictError, 409),
    (BusinessRuleViolationError, 422),
    (AuthenticationError, 401),
    (AuthorizationError, 403),
    (ExternalServiceUnavailableError, 503),
)


def status_for(error: DomainError) -> int:
    for error_type, status in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return status
    return 400


def error_response(
    request: Request, status: int, code: str, message: str, details: object | None = None
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    body = {"error": {"code": code, "message": message, "details": details, "requestId": request_id}}
    return JSONResponse(status_code=status, content=body)


async def _domain_error_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, DomainError)
    status = status_for(error)
    log = logger.warning if status >= 500 else logger.info
    log("request rejected", extra={"code": error.code, "status": status, "path": request.url.path})
    return error_response(request, status, error.code, error.message, error.details or None)


async def _validation_error_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    issues = [
        {"field": ".".join(str(part) for part in item["loc"][1:]), "message": item["msg"]} for item in error.errors()
    ]
    first = issues[0] if issues else {"field": "", "message": "Solicitud inválida"}
    message = f"Datos inválidos en '{first['field']}': {first['message']}"
    return error_response(request, 422, "validation_error", message, issues)


async def _http_error_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
    return error_response(request, error.status_code, "http_error", str(error.detail))


async def _unhandled_error_handler(request: Request, error: Exception) -> JSONResponse:
    logger.exception("unhandled error", extra={"path": request.url.path})
    return error_response(request, 500, "internal_error", "Error interno del servidor.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
