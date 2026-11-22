from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.domain.entities.refresh_session import RefreshSession
from app.modules.identity.domain.entities.user import User
from app.modules.identity.domain.value_objects.email import Email
from app.modules.identity.domain.value_objects.role import Role
from app.modules.identity.infrastructure.persistence.user_model import RefreshSessionModel, UserModel


def _user_to_domain(model: UserModel) -> User:
    return User(
        id=model.id,
        email=Email(model.email),
        full_name=model.full_name,
        password_hash=model.password_hash,
        role=Role(model.role),
        is_active=model.is_active,
        created_at=model.created_at,
        telegram_chat_id=model.telegram_chat_id,
        failed_login_attempts=model.failed_login_attempts,
        locked_until=model.locked_until,
    )


def _copy_user(user: User, model: UserModel) -> UserModel:
    model.id = user.id
    model.email = user.email.value
    model.full_name = user.full_name
    model.password_hash = user.password_hash
    model.role = user.role.value
    model.is_active = user.is_active
    model.telegram_chat_id = user.telegram_chat_id
    model.failed_login_attempts = user.failed_login_attempts
    model.locked_until = user.locked_until
    model.created_at = user.created_at
    return model


class PostgresUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return _user_to_domain(model) if model else None

    async def get_by_email(self, email: Email) -> User | None:
        model = await self._session.scalar(select(UserModel).where(UserModel.email == email.value))
        return _user_to_domain(model) if model else None

    async def list_all(self) -> list[User]:
        rows = await self._session.scalars(select(UserModel).order_by(UserModel.full_name))
        return [_user_to_domain(row) for row in rows]

    async def add(self, user: User) -> None:
        self._session.add(_copy_user(user, UserModel()))
        await self._session.flush()

    async def save(self, user: User) -> None:
        model = await self._session.get(UserModel, user.id)
        if model is None:
            await self.add(user)
            return
        _copy_user(user, model)
        await self._session.flush()


def _session_to_domain(model: RefreshSessionModel) -> RefreshSession:
    return RefreshSession(
        id=model.id,
        user_id=model.user_id,
        family_id=model.family_id,
        token_hash=model.token_hash,
        created_at=model.created_at,
        expires_at=model.expires_at,
        revoked_at=model.revoked_at,
    )


class PostgresRefreshSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_token_hash(self, token_hash: str) -> RefreshSession | None:
        model = await self._session.scalar(
            select(RefreshSessionModel).where(RefreshSessionModel.token_hash == token_hash)
        )
        return _session_to_domain(model) if model else None

    async def add(self, session: RefreshSession) -> None:
        self._session.add(
            RefreshSessionModel(
                id=session.id,
                user_id=session.user_id,
                family_id=session.family_id,
                token_hash=session.token_hash,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
            )
        )
        await self._session.flush()

    async def save(self, session: RefreshSession) -> None:
        model = await self._session.get(RefreshSessionModel, session.id)
        if model is None:
            await self.add(session)
            return
        model.revoked_at = session.revoked_at
        await self._session.flush()

    async def revoke_family(self, family_id: uuid.UUID, now: datetime) -> None:
        await self._session.execute(
            update(RefreshSessionModel)
            .where(RefreshSessionModel.family_id == family_id, RefreshSessionModel.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_all_for_user(self, user_id: uuid.UUID, now: datetime) -> None:
        await self._session.execute(
            update(RefreshSessionModel)
            .where(RefreshSessionModel.user_id == user_id, RefreshSessionModel.revoked_at.is_(None))
            .values(revoked_at=now)
        )
