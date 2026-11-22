"""Jerarquía de errores semánticos que comparten todos los módulos.

El dominio y la aplicación lanzan estos errores sin saber de tecnología. Solo la capa
de presentación los convierte en códigos HTTP (ver app/core/http/error_handlers.py),
por eso el dominio nunca importa HTTPException.
"""

from __future__ import annotations

from collections.abc import Mapping


class DomainError(Exception):
    """Clase base. code es un identificador estable que se puede leer por máquina."""

    code: str = "domain_error"

    def __init__(self, message: str, *, details: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, object] = dict(details or {})


class EntityNotFoundError(DomainError):
    code = "not_found"


class ConflictError(DomainError):
    """La petición es válida pero choca con el estado actual (duplicados, iniciar dos veces...)."""

    code = "conflict"


class BusinessRuleViolationError(DomainError):
    """La entrada está bien formada pero rompe una invariante del dominio."""

    code = "business_rule_violation"
