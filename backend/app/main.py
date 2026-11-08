from fastapi import FastAPI

from backend.app.api.health import router as health_router
from backend.app.catalog.api import router as catalog_router
from backend.app.core.config import get_settings
from backend.app.finance.accounts_api import router as finance_accounts_router
from backend.app.finance.api import router as finance_router
from backend.app.finance.periods_api import router as finance_periods_router
from backend.app.finance.reports_api import router as finance_reports_router
from backend.app.identity.access_api import router as access_router
from backend.app.identity.api import router as auth_router
from backend.app.identity.invitation_api import router as invitation_router
from backend.app.modules.api import router as modules_router
from backend.app.inventory.api import router as inventory_router
from backend.app.procurement.api import router as procurement_router
from backend.app.version import PRODUCT_VERSION


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=PRODUCT_VERSION,
        description="AI Business Studio API",
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(catalog_router, prefix="/api/v1")
    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(access_router, prefix="/api/v1")
    application.include_router(invitation_router, prefix="/api/v1")
    application.include_router(modules_router, prefix="/api/v1")
    application.include_router(finance_router, prefix="/api/v1")
    application.include_router(finance_accounts_router, prefix="/api/v1")
    application.include_router(finance_periods_router, prefix="/api/v1")
    application.include_router(finance_reports_router, prefix="/api/v1")
    application.include_router(inventory_router, prefix="/api/v1")
    application.include_router(procurement_router, prefix="/api/v1")
    return application


app = create_app()
