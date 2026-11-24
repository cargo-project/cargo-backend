from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.modules.identity.domain.value_objects.email import Email
from app.modules.identity.domain.value_objects.role import Role
from app.shared.domain.entity import Entity
from app.shared.domain.errors import BusinessRuleViolationError


@dataclass(eq=False)
class User(Entity):
    """Raíz de agregado del contexto de identidad.

    Acá vive el estado contra fuerza bruta: la regla de bloqueo tiene que cumplirse
    sin importar qué caso de uso autentique al usuario.
    """

    id: uuid.UUID
    email: Email
    full_name: str
    password_hash: str
    role: Role
    is_active: bool
    created_at: datetime
    telegram_chat_id: str | None = None
    failed_login_attempts: int = 0
    locked_until: datetime | None = None

    @classmethod
    def register(
        cls,
        *,
        email: Email,
        full_name: str,
        password_hash: str,
        role: Role,
        now: datetime,
        telegram_chat_id: str | None = None,
        is_active: bool = True,
    ) -> User:
        return cls(
            id=uuid.uuid4(),
            email=email,
            full_name=cls._clean_name(full_name),
            password_hash=password_hash,
            role=role,
            is_active=is_active,
            created_at=now,
            telegram_chat_id=telegram_chat_id,
        )

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and now < self.locked_until

    def can_authenticate(self, now: datetime) -> bool:
        return self.is_active and not self.is_locked(now)

    def record_failed_login(self, now: datetime, *, max_attempts: int, lockout: timedelta) -> None:
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = now + lockout
            self.failed_login_attempts = 0

    def record_successful_login(self) -> None:
        self.failed_login_attempts = 0
        self.locked_until = None

    def change_password_hash(self, password_hash: str) -> None:
        self.password_hash = password_hash

    def update_profile(
        self,
        *,
        full_name: str | None = None,
        role: Role | None = None,
        is_active: bool | None = None,
        telegram_chat_id: str | None = None,
    ) -> None:
        if full_name is not None:
            self.full_name = self._clean_name(full_name)
        if role is not None:
            self.role = role
        if is_active is not None:
            self.is_active = is_active
        if telegram_chat_id is not None:
            self.telegram_chat_id = telegram_chat_id.strip() or None

    @staticmethod
    def _clean_name(full_name: str) -> str:
        cleaned = " ".join(full_name.split())
        if not 2 <= len(cleaned) <= 120:
            raise BusinessRuleViolationError("El nombre debe tener entre 2 y 120 caracteres.")
        return cleaned
