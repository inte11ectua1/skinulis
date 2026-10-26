import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.system import router
from app.config import Settings
from app.db import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()
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
    application.include_router(router)
    return application
