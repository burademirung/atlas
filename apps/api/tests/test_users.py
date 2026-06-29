import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas_api.auth.passwords import PasswordHasher
from atlas_api.users.repository import UserRepository
from atlas_api.users.service import DuplicateEmailError, UserService


def make_service(session: AsyncSession) -> UserService:
    return UserService(UserRepository(session), PasswordHasher(19456, 2, 1))


async def test_register_then_authenticate(db_session: AsyncSession) -> None:
    svc = make_service(db_session)
    user = await svc.register("reg@example.com", "hunter2hunter2")
    assert user.id is not None
    assert await svc.authenticate("reg@example.com", "hunter2hunter2") is not None
    assert await svc.authenticate("reg@example.com", "wrong") is None


async def test_duplicate_email_rejected(db_session: AsyncSession) -> None:
    svc = make_service(db_session)
    await svc.register("dup@example.com", "password123x")
    with pytest.raises(DuplicateEmailError):
        await svc.register("dup@example.com", "password123x")
