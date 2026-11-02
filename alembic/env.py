from logging.config import fileConfig

from alembic import context
from app.config import Settings
from app.db import Database
from app.models import Base

config = context.config
if config.config_file_name is not None and not config.attributes.get("safe_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = Settings()
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url=settings.get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    database = Database(settings)
    try:
        with database.engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        database.close()
