from atlas_api.auth.passwords import PasswordHasher


def make_hasher() -> PasswordHasher:
    return PasswordHasher(memory_kib=19456, time_cost=2, parallelism=1)


def test_hash_roundtrip() -> None:
    h = make_hasher()
    hashed = h.hash("correct horse battery staple")
    assert hashed.startswith("$argon2id$")
    assert h.verify("correct horse battery staple", hashed) is True


def test_wrong_password_fails() -> None:
    h = make_hasher()
    hashed = h.hash("right")
    assert h.verify("wrong", hashed) is False
