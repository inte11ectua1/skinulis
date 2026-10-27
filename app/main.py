import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.auth import router as auth_router
from app.api.system import router
from app.config import Settings
from app.core.errors import install_error_handlers
from app.db import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()
    configuration.require_jwt_secret()
    logging.getLogger("app").setLevel(configuration.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database = Database(configuration)
        application.state.database = database
        try:
            yield
        finally:
            database.close()

    application = FastAPI(title="Скинулись", version=__version__, lifespan=lifespan)
    application.state.settings = configuration
    install_error_handlers(application)
    application.include_router(router)
    application.include_router(auth_router)
    return application
