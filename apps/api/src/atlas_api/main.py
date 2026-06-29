from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from atlas_api.errors import install_error_handlers
from atlas_api.health.router import router as health_router
from atlas_api.logging import configure_logging
from atlas_api.middleware import request_id_middleware


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Atlas API", version="0.1.0")
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_middleware)
    install_error_handlers(app)
    app.include_router(health_router)
    return app


app = create_app()
