"""Dependencias de autenticación/autorización que reutilizan todos los routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.composition import identity_factory
from app.core.http.dependencies import ScopeDep
from app.core.security.http_security_middleware import ACCESS_COOKIE
from app.modules.identity.application.auth_errors import InvalidSessionError
from app.modules.identity.application.dto.identity_dto import UserDTO
from app.shared.application.errors import AuthorizationError


async def get_current_user(request: Request, scope: ScopeDep) -> UserDTO:
    """Saca el usuario de la cookie cargo_access.

    El usuario se vuelve a leer de la BD para que una desactivación aplique al
    instante y no recién cuando venza el token.
    """
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise InvalidSessionError()
    claims = scope.resources.token_provider.decode_access_token(token)
    user = await identity_factory.get_current_user(scope).execute(claims.user_id)
    if not user.is_active:
        raise InvalidSessionError()
    return user


CurrentUser = Annotated[UserDTO, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> UserDTO:
    if user.role != "ADMIN":
        raise AuthorizationError("Esta operación requiere el rol ADMIN.")
    return user


AdminUser = Annotated[UserDTO, Depends(require_admin)]
