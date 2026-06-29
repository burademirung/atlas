from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str
    redis_url: str
    jwt_secret: str

    jwt_issuer: str = "atlas"
    jwt_audience: str = "atlas-api"
    jwt_algorithm: str = "HS256"
    access_ttl_seconds: int = 600
    refresh_ttl_seconds: int = 1_209_600  # 14 days

    argon2_memory_kib: int = 19_456
    argon2_time_cost: int = 2
    argon2_parallelism: int = 1

    environment: str = "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
