from atlas_api.auth.passwords import PasswordHasher
from atlas_api.db.models import User
from atlas_api.users.repository import UserRepository


class DuplicateEmailError(Exception):
    pass


class UserService:
    def __init__(self, repo: UserRepository, hasher: PasswordHasher) -> None:
        self._repo = repo
        self._hasher = hasher

    async def register(self, email: str, password: str) -> User:
        normalized = email.strip().lower()
        if await self._repo.get_by_email(normalized) is not None:
            raise DuplicateEmailError(normalized)
        return await self._repo.create(normalized, self._hasher.hash(password))

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self._repo.get_by_email(email.strip().lower())
        if user is None:
            return None
        if not self._hasher.verify(password, user.password_hash):
            return None
        return user
