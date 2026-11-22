"""Manejo de cookies de sesión (es tema HTTP, por eso va en presentación)."""

from __future__ import annotations

import secrets

from fastapi import Response

from app.core.config.settings import Settings
from app.core.security.http_security_middleware import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
from app.modules.identity.application.dto.identity_dto import AuthenticatedSession


def set_session_cookies(response: Response, session: AuthenticatedSession, settings: Settings) -> None:
    access_max_age = settings.access_token_ttl_seconds
    refresh_max_age = settings.refresh_token_ttl_seconds
    response.set_cookie(
        ACCESS_COOKIE,
        session.access_token,
        max_age=access_max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    # El path cubre toda la API para que el handshake del WebSocket pueda revalidar un
    # access token vencido sin exponer la cookie a las páginas del frontend.
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=settings.api_prefix,
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=refresh_max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=settings.api_prefix)
    response.delete_cookie(CSRF_COOKIE, path="/")
