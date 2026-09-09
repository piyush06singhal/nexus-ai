"""Database engine, session management, and declarative base.

Establishes the SQLAlchemy engine and session factory used across the app.
The declarative `Base` is the foundation for all persisted models (users,
organizations, agents, tasks, etc.) added in later phases.
"""

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# Stable naming convention so Alembic generates consistent constraint names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Engine configured for PostgreSQL. pool_pre_ping detects dead connections.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)

# Session factory — each session is short-lived and yielded via get_db().
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

# Sync session factory for worker/scheduler threads (independent sessions).
sync_session_factory = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and closes it after.

    The session is always cleaned up even if the request handler raises.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
