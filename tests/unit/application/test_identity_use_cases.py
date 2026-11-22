from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.identity.application.auth_errors import InvalidCredentialsError, InvalidSessionError
from app.modules.identity.application.dto.identity_dto import LoginCommand
from app.modules.identity.application.use_cases.authenticate_user import AuthenticateUserUseCase, LoginPolicy
from app.modules.identity.application.use_cases.refresh_session import RefreshSessionUseCase
from app.modules.identity.domain.entities.refresh_session import RefreshSession
from app.modules.identity.domain.entities.user import User
from app.modules.identity.domain.value_objects.email import Email
from app.modules.identity.domain.value_objects.role import Role
from app.modules.identity.infrastructure.security.jwt_token_provider import JwtTokenProvider
from tests.unit.fakes import T0, FakeClock, FakeUnitOfWork, RecordingAuditLog


class PlainHasher:
    """Doble de prueba rápido (en producción se usa Argon2id)."""

    def hash(self, password: str) -> str:
        return f"plain:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"plain:{password}"

    def needs_rehash(self, password_hash: str) -> bool:
        return False

    def verify_against_dummy(self, password: str) -> None:
        return None


class Users:
    def __init__(self, user: User) -> None:
        self.user = user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.user if user_id == self.user.id else None

    async def get_by_email(self, email: Email) -> User | None:
        return self.user if email == self.user.email else None

    async def list_all(self) -> list[User]:
        return [self.user]

    async def add(self, user: User) -> None:
        self.user = user

    async def save(self, user: User) -> None:
        self.user = user


class Sessions:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, RefreshSession] = {}

    async def get_by_token_hash(self, token_hash: str) -> RefreshSession | None:
        return next((s for s in self.items.values() if s.token_hash == token_hash), None)

    async def add(self, session: RefreshSession) -> None:
        self.items[session.id] = session

    async def save(self, session: RefreshSession) -> None:
        self.items[session.id] = session

    async def revoke_family(self, family_id: uuid.UUID, now: object) -> None:
        for s in self.items.values():
            if s.family_id == family_id and s.revoked_at is None:
                s.revoked_at = now  # type: ignore[assignment]

    async def revoke_all_for_user(self, user_id: uuid.UUID, now: object) -> None:
        for s in self.items.values():
            if s.user_id == user_id:
                s.revoked_at = now  # type: ignore[assignment]


TOKENS = JwtTokenProvider(secret="x" * 40, algorithm="HS256", issuer="test", access_ttl=timedelta(minutes=15))
POLICY = LoginPolicy(max_failed_attempts=3, lockout=timedelta(minutes=15), refresh_ttl=timedelta(days=7))


@pytest.fixture
def setup() -> tuple[Users, Sessions, FakeClock]:
    user = User.register(
        email=Email("admin@cargo.pe"), full_name="Admin", password_hash="plain:correct-horse", role=Role.ADMIN, now=T0
    )
    return Users(user), Sessions(), FakeClock(datetime.now(UTC))


def _login(users: Users, sessions: Sessions, clock: FakeClock) -> AuthenticateUserUseCase:
    return AuthenticateUserUseCase(
        users, sessions, PlainHasher(), TOKENS, FakeUnitOfWork(), clock, RecordingAuditLog(), POLICY
    )


async def test_login_issues_tokens(setup: tuple[Users, Sessions, FakeClock]) -> None:
    users, sessions, clock = setup
    session = await _login(users, sessions, clock).execute(LoginCommand("ADMIN@cargo.pe", "correct-horse"))
    assert session.user.role == "ADMIN"
    assert TOKENS.decode_access_token(session.access_token).user_id == users.user.id
    assert len(sessions.items) == 1
    assert next(iter(sessions.items.values())).token_hash != session.refresh_token  # solo se guarda el hash


async def test_wrong_password_and_lockout(setup: tuple[Users, Sessions, FakeClock]) -> None:
    users, sessions, clock = setup
    use_case = _login(users, sessions, clock)
    for _ in range(3):
        with pytest.raises(InvalidCredentialsError):
            await use_case.execute(LoginCommand("admin@cargo.pe", "wrong"))
    with pytest.raises(InvalidCredentialsError):  # contraseña correcta, pero la cuenta ya está bloqueada
        await use_case.execute(LoginCommand("admin@cargo.pe", "correct-horse"))
    clock.advance(16 * 60)
    assert (await use_case.execute(LoginCommand("admin@cargo.pe", "correct-horse"))).user.email == "admin@cargo.pe"


async def test_unknown_user_gets_same_error(setup: tuple[Users, Sessions, FakeClock]) -> None:
    users, sessions, clock = setup
    with pytest.raises(InvalidCredentialsError):
        await _login(users, sessions, clock).execute(LoginCommand("ghost@cargo.pe", "whatever"))


async def test_refresh_rotates_and_detects_reuse(setup: tuple[Users, Sessions, FakeClock]) -> None:
    users, sessions, clock = setup
    login = await _login(users, sessions, clock).execute(LoginCommand("admin@cargo.pe", "correct-horse"))
    refresh = RefreshSessionUseCase(users, sessions, TOKENS, FakeUnitOfWork(), clock, timedelta(days=7))
    rotated = await refresh.execute(login.refresh_token)
    assert rotated.refresh_token != login.refresh_token
    with pytest.raises(InvalidSessionError):  # reenvían un token viejo robado
        await refresh.execute(login.refresh_token)
    with pytest.raises(InvalidSessionError):  # se revoca toda la familia
        await refresh.execute(rotated.refresh_token)


def test_tampered_access_token_is_rejected() -> None:
    token = TOKENS.issue_access_token(user_id=uuid.uuid4(), role="ADMIN", now=datetime.now(UTC)).value
    other = JwtTokenProvider(secret="y" * 40, algorithm="HS256", issuer="test", access_ttl=timedelta(minutes=15))
    with pytest.raises(InvalidSessionError):
        other.decode_access_token(token)
