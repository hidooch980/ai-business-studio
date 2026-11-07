from fastapi import FastAPI

from backend.app.api.health import router as health_router
from backend.app.core.config import get_settings
from backend.app.identity.api import router as auth_router


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AI Business Studio API",
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(auth_router, prefix="/api/v1")
    return application


app = create_app()
