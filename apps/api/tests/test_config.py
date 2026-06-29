import importlib

from atlas_api import config


def test_settings_load_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    importlib.reload(config)
    config.get_settings.cache_clear()
    s = config.get_settings()
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_issuer == "atlas"
    assert s.jwt_audience == "atlas-api"
    assert s.access_ttl_seconds == 600
    assert s.argon2_memory_kib == 19456


def test_settings_require_secret(monkeypatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    config.get_settings.cache_clear()
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        config.Settings()
