"""Database models package.

Import every model here so that SQLAlchemy's metadata and Alembic's
``target_metadata`` can discover all mapped tables.
"""

from app.db.models.agent import Agent

__all__ = ["Agent"]
