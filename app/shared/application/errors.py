"""Errores de aplicación que no son invariantes de dominio."""

from __future__ import annotations

from app.shared.domain.errors import DomainError


class AuthenticationError(DomainError):
    code = "authentication_failed"


class AuthorizationError(DomainError):
    code = "forbidden"


class ExternalServiceUnavailableError(DomainError):
    """Un proveedor externo necesario (Mapbox, Telegram...) no responde o no está configurado."""

    code = "external_service_unavailable"
