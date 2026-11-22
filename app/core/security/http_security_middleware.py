"""Middleware de seguridad HTTP: request id, chequeo CSRF (double submit) y cabeceras de endurecimiento."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.http.error_handlers import error_response

ACCESS_COOKIE: Final = "cargo_access"
REFRESH_COOKIE: Final = "cargo_refresh"
CSRF_COOKIE: Final = "cargo_csrf"
CSRF_HEADER: Final = "X-CSRF-Token"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class HttpSecurityMiddleware(BaseHTTPMiddleware):
    """Aplica las protecciones HTTP generales antes de que corra cualquier router.

    CSRF: la sesión vive en cookies, así que toda petición que cambia datos tiene que
    devolver la cookie legible cargo_csrf en la cabecera X-CSRF-Token.
    Se exceptúan /auth/login (todavía no hay sesión) y /auth/refresh (el frontend lo
    llama sin la cabecera y su cookie es SameSite=Strict).
    """

    def __init__(self, app: object, *, api_prefix: str) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._csrf_exempt = {f"{api_prefix}/auth/login", f"{api_prefix}/auth/refresh"}

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        if self._requires_csrf(request) and not self._csrf_valid(request):
            response: Response = error_response(request, 403, "csrf_failed", "Token CSRF ausente o inválido.")
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def _requires_csrf(self, request: Request) -> bool:
        if request.method in _SAFE_METHODS or request.url.path in self._csrf_exempt:
            return False
        # Sin cookies de sesión no hay nada que aprovechar con CSRF;
        # el endpoint igual va a responder 401.
        return ACCESS_COOKIE in request.cookies or REFRESH_COOKIE in request.cookies

    @staticmethod
    def _csrf_valid(request: Request) -> bool:
        cookie = request.cookies.get(CSRF_COOKIE, "")
        header = request.headers.get(CSRF_HEADER, "")
        return bool(cookie) and secrets.compare_digest(cookie, header)
