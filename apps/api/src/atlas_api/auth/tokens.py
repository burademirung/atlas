import time
import uuid
from dataclasses import dataclass

import jwt
from redis.asyncio import Redis

from atlas_api.config import Settings
from atlas_api.errors import ProblemException


@dataclass
class TokenPair:
    access: str
    refresh: str


@dataclass
class Claims:
    sub: str
    jti: str
    family: str
    typ: str


def _used_key(family: str, jti: str) -> str:
    return f"refresh:used:{family}:{jti}"


def _family_revoked_key(family: str) -> str:
    return f"refresh:revoked-family:{family}"


def _denylist_key(jti: str) -> str:
    return f"access:revoked:{jti}"


class TokenService:
    def __init__(self, settings: Settings, redis: Redis) -> None:
        self._s = settings
        self._redis = redis

    def _encode(self, user_id: int, typ: str, ttl: int, family: str) -> str:
        now = int(time.time())
        payload = {
            "sub": str(user_id),
            "iss": self._s.jwt_issuer,
            "aud": self._s.jwt_audience,
            "iat": now,
            "exp": now + ttl,
            "jti": uuid.uuid4().hex,
            "family": family,
            "typ": typ,
        }
        return jwt.encode(payload, self._s.jwt_secret, algorithm=self._s.jwt_algorithm)

    def issue_pair(self, user_id: int) -> TokenPair:
        family = uuid.uuid4().hex
        return TokenPair(
            access=self._encode(user_id, "access", self._s.access_ttl_seconds, family),
            refresh=self._encode(user_id, "refresh", self._s.refresh_ttl_seconds, family),
        )

    def decode(self, token: str, expected_typ: str) -> Claims:
        try:
            data = jwt.decode(
                token,
                self._s.jwt_secret,
                algorithms=[self._s.jwt_algorithm],  # allowlist; rejects alg:none/others
                audience=self._s.jwt_audience,
                issuer=self._s.jwt_issuer,
                options={"require": ["exp", "iss", "aud", "sub", "jti"]},
            )
        except jwt.PyJWTError as exc:
            raise ProblemException(401, "Invalid token", str(exc)) from exc
        if data.get("typ") != expected_typ:
            raise ProblemException(401, "Wrong token type")
        return Claims(sub=data["sub"], jti=data["jti"], family=data["family"], typ=data["typ"])

    async def rotate_refresh(self, token: str) -> TokenPair:
        claims = self.decode(token, expected_typ="refresh")
        if await self._redis.exists(_family_revoked_key(claims.family)):
            raise ProblemException(401, "Token family revoked")
        # reuse detection: this refresh jti already consumed?
        already_used = await self._redis.set(
            _used_key(claims.family, claims.jti),
            "1",
            ex=self._s.refresh_ttl_seconds,
            nx=True,
        )
        if already_used is None:
            # jti was already used -> reuse attack: revoke the whole family
            await self._redis.set(
                _family_revoked_key(claims.family), "1", ex=self._s.refresh_ttl_seconds
            )
            raise ProblemException(401, "Refresh token reuse detected")
        new = self._encode(int(claims.sub), "refresh", self._s.refresh_ttl_seconds, claims.family)
        access = self._encode(int(claims.sub), "access", self._s.access_ttl_seconds, claims.family)
        return TokenPair(access=access, refresh=new)

    async def revoke_access(self, jti: str, ttl_seconds: int) -> None:
        await self._redis.set(_denylist_key(jti), "1", ex=ttl_seconds)

    async def is_revoked(self, jti: str) -> bool:
        return bool(await self._redis.exists(_denylist_key(jti)))
