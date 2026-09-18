from alembic import context

from data_police.config import settings
from data_police.db import Base, make_engine
from data_police import models  # noqa: F401


def offline():
    context.configure(
        url=settings.database_url, target_metadata=Base.metadata, literal_binds=True, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


def online():
    engine = make_engine(settings.database_url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            compare_type=True,
            render_as_batch=settings.database_url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


offline() if context.is_offline_mode() else online()
