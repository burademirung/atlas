from argon2 import PasswordHasher as _Argon2
from argon2 import Type
from argon2.exceptions import VerifyMismatchError


class PasswordHasher:
    def __init__(self, memory_kib: int, time_cost: int, parallelism: int) -> None:
        self._ph = _Argon2(
            type=Type.ID,
            memory_cost=memory_kib,
            time_cost=time_cost,
            parallelism=parallelism,
        )

    def hash(self, password: str) -> str:
        return self._ph.hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        try:
            return self._ph.verify(hashed, password)
        except VerifyMismatchError:
            return False
