from collections.abc import AsyncIterator

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from atlas_api.auth.tokens import TokenService
from atlas_api.db.models import User
from atlas_api.errors import ProblemException
from atlas_api.users.repository import UserRepository
from atlas_api.users.service import UserService


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    maker = request.app.state.sessionmaker
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_redis(request: Request) -> Redis:
    return request.app.state.redis  # type: ignore[no-any-return]


def get_token_service(request: Request, redis: Redis = Depends(get_redis)) -> TokenService:
    return TokenService(request.app.state.settings, redis)


def get_user_service(
    request: Request, session: AsyncSession = Depends(get_session)
) -> UserService:
    return UserService(UserRepository(session), request.app.state.hasher)


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
    tokens: TokenService = Depends(get_token_service),
) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise ProblemException(401, "Missing bearer token")
    claims = tokens.decode(auth.removeprefix("Bearer "), expected_typ="access")
    if await tokens.is_revoked(claims.jti):
        raise ProblemException(401, "Token revoked")
    user = await UserRepository(session).get_by_id(int(claims.sub))
    if user is None:
        raise ProblemException(401, "Unknown user")
    return user
