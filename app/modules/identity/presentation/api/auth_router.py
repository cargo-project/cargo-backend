from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.composition import identity_factory
from app.core.http.dependencies import ScopeDep
from app.core.http.envelope import ERROR_RESPONSES, DataEnvelope, wrap
from app.core.security.http_security_middleware import REFRESH_COOKIE
from app.modules.identity.application.dto.identity_dto import LoginCommand, UpdateUserCommand
from app.modules.identity.presentation.api.auth_cookies import (
    clear_session_cookies,
    set_session_cookies,
)
from app.modules.identity.presentation.api.auth_dependencies import CurrentUser
from app.modules.identity.presentation.schemas.identity_schemas import (
    ChangePasswordRequest,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    UpdateProfileRequest,
    UserResponse,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"], responses=ERROR_RESPONSES)


@auth_router.post("/login", summary="Log in and open a cookie-based session")
async def login(body: LoginRequest, response: Response, scope: ScopeDep) -> DataEnvelope[UserResponse]:
    session = await identity_factory.authenticate_user(scope).execute(
        LoginCommand(email=body.email, password=body.password)
    )
    set_session_cookies(response, session, scope.resources.settings)
    return wrap(UserResponse.from_dto(session.user))


@auth_router.post("/refresh", summary="Rotate the refresh token and renew the access token")
async def refresh(request: Request, response: Response, scope: ScopeDep) -> DataEnvelope[UserResponse]:
    session = await identity_factory.refresh_session(scope).execute(request.cookies.get(REFRESH_COOKIE))
    set_session_cookies(response, session, scope.resources.settings)
    return wrap(UserResponse.from_dto(session.user))


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Close the session")
async def logout(request: Request, response: Response, scope: ScopeDep) -> Response:
    await identity_factory.logout(scope).execute(request.cookies.get(REFRESH_COOKIE))
    response.status_code = status.HTTP_204_NO_CONTENT
    clear_session_cookies(response, scope.resources.settings)
    return response


@auth_router.get("/me", summary="Current authenticated user")
async def me(user: CurrentUser) -> DataEnvelope[UserResponse]:
    return wrap(UserResponse.from_dto(user))


@auth_router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change own password (revokes every session)",
)
async def change_password(
    body: ChangePasswordRequest, user: CurrentUser, response: Response, scope: ScopeDep
) -> Response:
    await identity_factory.change_password(scope).execute(
        user_id=user.id, current_password=body.current_password, new_password=body.new_password
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    clear_session_cookies(response, scope.resources.settings)
    return response


@auth_router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a one-time reset code to the account's Telegram (same answer whether the email exists or not)",
)
async def request_password_reset(body: PasswordResetRequest, scope: ScopeDep) -> DataEnvelope[dict[str, str]]:
    await identity_factory.request_password_reset(scope).execute(email=body.email)
    return wrap(
        {"message": "Si la cuenta existe y tiene Telegram vinculado, te enviamos un código. Revisa tu Telegram."}
    )


@auth_router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set a new password with the code received on Telegram (revokes every session)",
)
async def confirm_password_reset(body: PasswordResetConfirm, response: Response, scope: ScopeDep) -> Response:
    await identity_factory.confirm_password_reset(scope).execute(
        email=body.email, code=body.code, new_password=body.new_password
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    clear_session_cookies(response, scope.resources.settings)
    return response


@auth_router.patch("/me", summary="Update own name or recovery Telegram chat (the bot verifies the new chat)")
async def update_me(body: UpdateProfileRequest, user: CurrentUser, scope: ScopeDep) -> DataEnvelope[UserResponse]:
    updated = await identity_factory.update_user(scope).execute(
        UpdateUserCommand(user_id=user.id, full_name=body.full_name, telegram_chat_id=body.telegram_chat_id),
        actor_id=user.id,
    )
    return wrap(UserResponse.from_dto(updated))


@auth_router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Self sign-up: creates an inactive OPERATOR account pending administrator approval",
)
async def register(body: RegisterRequest, scope: ScopeDep) -> DataEnvelope[dict[str, str]]:
    await identity_factory.register_account(scope).execute(
        email=body.email, full_name=body.full_name, password=body.password, telegram_chat_id=body.telegram_chat_id
    )
    return wrap(
        {"message": "Tu solicitud fue registrada. Un administrador debe aprobar la cuenta; te avisaremos por Telegram."}
    )
