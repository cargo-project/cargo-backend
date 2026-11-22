from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.composition import identity_factory
from app.core.http.dependencies import ScopeDep
from app.core.http.envelope import ERROR_RESPONSES, DataEnvelope, wrap
from app.modules.identity.application.dto.identity_dto import CreateUserCommand, UpdateUserCommand
from app.modules.identity.presentation.api.auth_dependencies import AdminUser
from app.modules.identity.presentation.schemas.identity_schemas import (
    CreateUserRequest,
    UpdateUserRequest,
    UserResponse,
)

users_router = APIRouter(prefix="/users", tags=["users"], responses=ERROR_RESPONSES)


@users_router.get("", summary="List platform users (ADMIN)")
async def list_users(_: AdminUser, scope: ScopeDep) -> DataEnvelope[list[UserResponse]]:
    users = await identity_factory.list_users(scope).execute()
    return wrap([UserResponse.from_dto(user) for user in users])


@users_router.post("", status_code=status.HTTP_201_CREATED, summary="Create a user (ADMIN)")
async def create_user(body: CreateUserRequest, admin: AdminUser, scope: ScopeDep) -> DataEnvelope[UserResponse]:
    user = await identity_factory.create_user(scope).execute(
        CreateUserCommand(
            email=body.email,
            full_name=body.full_name,
            password=body.password,
            role=body.role,
            telegram_chat_id=body.telegram_chat_id,
        ),
        actor_id=admin.id,
    )
    return wrap(UserResponse.from_dto(user))


@users_router.patch("/{user_id}", summary="Update role, status or profile (ADMIN)")
async def update_user(
    user_id: uuid.UUID, body: UpdateUserRequest, admin: AdminUser, scope: ScopeDep
) -> DataEnvelope[UserResponse]:
    user = await identity_factory.update_user(scope).execute(
        UpdateUserCommand(
            user_id=user_id,
            full_name=body.full_name,
            role=body.role,
            is_active=body.is_active,
            telegram_chat_id=body.telegram_chat_id,
        ),
        actor_id=admin.id,
    )
    return wrap(UserResponse.from_dto(user))
