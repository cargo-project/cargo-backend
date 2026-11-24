from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.domain.entities.password_reset import PasswordResetCode
from app.modules.identity.infrastructure.persistence.password_reset_model import PasswordResetCodeModel


def _to_domain(m: PasswordResetCodeModel) -> PasswordResetCode:
    return PasswordResetCode(
        id=m.id,
        user_id=m.user_id,
        code_hash=m.code_hash,
        created_at=m.created_at,
        expires_at=m.expires_at,
        attempts=m.attempts,
        used_at=m.used_at,
    )


class PostgresPasswordResetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest_for_user(self, user_id: uuid.UUID) -> PasswordResetCode | None:
        m = await self._session.scalar(
            select(PasswordResetCodeModel)
            .where(PasswordResetCodeModel.user_id == user_id)
            .order_by(PasswordResetCodeModel.created_at.desc())
            .limit(1)
        )
        return _to_domain(m) if m is not None else None

    async def count_issued_since(self, user_id: uuid.UUID, since: datetime) -> int:
        count = await self._session.scalar(
            select(func.count())
            .select_from(PasswordResetCodeModel)
            .where(PasswordResetCodeModel.user_id == user_id, PasswordResetCodeModel.created_at >= since)
        )
        return int(count or 0)

    async def invalidate_open_for_user(self, user_id: uuid.UUID, now: datetime) -> None:
        await self._session.execute(
            update(PasswordResetCodeModel)
            .where(PasswordResetCodeModel.user_id == user_id, PasswordResetCodeModel.used_at.is_(None))
            .values(used_at=now)
        )

    async def add(self, code: PasswordResetCode) -> None:
        self._session.add(
            PasswordResetCodeModel(
                id=code.id,
                user_id=code.user_id,
                code_hash=code.code_hash,
                created_at=code.created_at,
                expires_at=code.expires_at,
                attempts=code.attempts,
                used_at=code.used_at,
            )
        )
        await self._session.flush()

    async def save(self, code: PasswordResetCode) -> None:
        m = await self._session.get(PasswordResetCodeModel, code.id)
        if m is None:
            return
        m.attempts = code.attempts
        m.used_at = code.used_at
        await self._session.flush()
