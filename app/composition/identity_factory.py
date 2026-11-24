"""Arma los casos de uso de identidad con sus adaptadores reales."""

from __future__ import annotations

from datetime import timedelta

from app.composition.scope import Scope
from app.modules.identity.application.use_cases.authenticate_user import (
    AuthenticateUserUseCase,
    LoginPolicy,
)
from app.modules.identity.application.use_cases.change_password import ChangePasswordUseCase
from app.modules.identity.application.use_cases.logout import LogoutUseCase
from app.modules.identity.application.use_cases.manage_users import (
    CreateUserUseCase,
    GetCurrentUserUseCase,
    ListUsersUseCase,
    RegisterAccountUseCase,
    UpdateUserUseCase,
)
from app.modules.identity.application.use_cases.password_reset import (
    ConfirmPasswordResetUseCase,
    RequestPasswordResetUseCase,
)
from app.modules.identity.application.use_cases.refresh_session import (
    RefreshSessionUseCase,
    ValidateRefreshSessionUseCase,
)
from app.modules.identity.infrastructure.persistence.postgres_password_reset_repository import (
    PostgresPasswordResetRepository,
)
from app.modules.identity.infrastructure.persistence.postgres_user_repository import (
    PostgresRefreshSessionRepository,
    PostgresUserRepository,
)
from app.modules.identity.infrastructure.telegram_user_messenger import TelegramUserMessenger


def _messenger(scope: Scope) -> TelegramUserMessenger:
    return TelegramUserMessenger(scope.resources.notification_gateway)


def _users(scope: Scope) -> PostgresUserRepository:
    return PostgresUserRepository(scope.session)


def _sessions(scope: Scope) -> PostgresRefreshSessionRepository:
    return PostgresRefreshSessionRepository(scope.session)


def authenticate_user(scope: Scope) -> AuthenticateUserUseCase:
    settings = scope.resources.settings
    return AuthenticateUserUseCase(
        users=_users(scope),
        sessions=_sessions(scope),
        hasher=scope.resources.password_hasher,
        tokens=scope.resources.token_provider,
        uow=scope.uow,
        clock=scope.resources.clock,
        audit=scope.audit,
        policy=LoginPolicy(
            max_failed_attempts=settings.login_max_failed_attempts,
            lockout=timedelta(seconds=settings.login_lockout_seconds),
            refresh_ttl=timedelta(seconds=settings.refresh_token_ttl_seconds),
        ),
    )


def refresh_session(scope: Scope) -> RefreshSessionUseCase:
    return RefreshSessionUseCase(
        users=_users(scope),
        sessions=_sessions(scope),
        tokens=scope.resources.token_provider,
        uow=scope.uow,
        clock=scope.resources.clock,
        refresh_ttl=timedelta(seconds=scope.resources.settings.refresh_token_ttl_seconds),
    )


def validate_refresh_session(scope: Scope) -> ValidateRefreshSessionUseCase:
    return ValidateRefreshSessionUseCase(
        _sessions(scope), scope.resources.token_provider, _users(scope), scope.resources.clock
    )


def logout(scope: Scope) -> LogoutUseCase:
    return LogoutUseCase(_sessions(scope), scope.resources.token_provider, scope.uow, scope.resources.clock)


def change_password(scope: Scope) -> ChangePasswordUseCase:
    return ChangePasswordUseCase(
        _users(scope),
        _sessions(scope),
        scope.resources.password_hasher,
        scope.uow,
        scope.resources.clock,
        scope.audit,
    )


def get_current_user(scope: Scope) -> GetCurrentUserUseCase:
    return GetCurrentUserUseCase(_users(scope))


def list_users(scope: Scope) -> ListUsersUseCase:
    return ListUsersUseCase(_users(scope))


def create_user(scope: Scope) -> CreateUserUseCase:
    return CreateUserUseCase(
        _users(scope),
        scope.resources.password_hasher,
        scope.uow,
        scope.resources.clock,
        scope.audit,
        _messenger(scope),
    )


def update_user(scope: Scope) -> UpdateUserUseCase:
    return UpdateUserUseCase(_users(scope), scope.uow, scope.audit, _messenger(scope))


def request_password_reset(scope: Scope) -> RequestPasswordResetUseCase:
    return RequestPasswordResetUseCase(
        _users(scope),
        PostgresPasswordResetRepository(scope.session),
        scope.resources.password_hasher,
        _messenger(scope),
        scope.uow,
        scope.resources.clock,
        scope.audit,
    )


def confirm_password_reset(scope: Scope) -> ConfirmPasswordResetUseCase:
    return ConfirmPasswordResetUseCase(
        _users(scope),
        PostgresPasswordResetRepository(scope.session),
        _sessions(scope),
        scope.resources.password_hasher,
        _messenger(scope),
        scope.uow,
        scope.resources.clock,
        scope.audit,
    )


def register_account(scope: Scope) -> RegisterAccountUseCase:
    return RegisterAccountUseCase(
        _users(scope),
        scope.resources.password_hasher,
        scope.uow,
        scope.resources.clock,
        scope.audit,
        _messenger(scope),
    )
