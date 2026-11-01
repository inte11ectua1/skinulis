from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.auth import router as auth_router
from app.api.balances import build_router as build_balance_router
from app.api.expenses import build_router as build_expense_router
from app.api.groups import build_router
from app.api.settlement_notifications import router as notification_router
from app.api.settlements import build_router as build_settlement_router
from app.api.system import router
from app.api.telegram_identity import router as telegram_router
from app.config import Settings
from app.core.errors import install_error_handlers
from app.db import Database
from skinulis_logging import Event, configure_logging, emit, register_routes


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging("api")
    configuration = settings if settings is not None else Settings()
    configuration.require_jwt_secret()
    configuration.require_bot_service_token()
    configure_logging("api", configuration.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database = Database(configuration)
        application.state.database = database
        emit(Event.API_STARTED)
        try:
            yield
        finally:
            database.close()
            emit(Event.API_STOPPED)

    application = FastAPI(title="Скинулись", version=__version__, lifespan=lifespan)
    application.state.settings = configuration
    install_error_handlers(application)
    application.include_router(router)
    application.include_router(auth_router)
    application.include_router(build_router())
    application.include_router(build_router(internal=True))
    application.include_router(build_expense_router())
    application.include_router(build_expense_router(internal=True))
    application.include_router(build_balance_router())
    application.include_router(build_balance_router(internal=True))
    application.include_router(build_settlement_router())
    application.include_router(build_settlement_router(internal=True))
    application.include_router(notification_router)
    application.include_router(telegram_router)
    register_routes(
        [*application.openapi()["paths"], "/docs", "/redoc", "/openapi.json"]
    )
    return application
