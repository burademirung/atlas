from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.base import BaseHTTPMiddleware

from atlas_api.auth.passwords import PasswordHasher
from atlas_api.auth.router import router as auth_router
from atlas_api.config import get_settings
from atlas_api.db.engine import create_engine, session_factory
from atlas_api.errors import install_error_handlers
from atlas_api.health.router import router as health_router
from atlas_api.logging import configure_logging
from atlas_api.middleware import request_id_middleware


def create_app(engine: AsyncEngine | None = None, redis_url: str | None = None) -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Settings are read at startup (not at build time) so the app object can be
        # constructed in tests without a full environment.
        settings = get_settings()
        app.state.settings = settings
        app.state.hasher = PasswordHasher(
            settings.argon2_memory_kib, settings.argon2_time_cost, settings.argon2_parallelism
        )
        app.state.engine = engine or create_engine(settings.database_url)
        app.state.sessionmaker = session_factory(app.state.engine)
        app.state.redis = Redis.from_url(redis_url or settings.redis_url, decode_responses=True)
        try:
            yield
        finally:
            await app.state.redis.aclose()
            if engine is None:
                await app.state.engine.dispose()

    app = FastAPI(title="Atlas API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_middleware)
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router, prefix="/v1")
    return app


app = create_app()
