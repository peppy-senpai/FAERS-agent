"""Database connection setup for the FAERS Agent backend.

Centralises the SQLAlchemy engine so every module shares one connection pool.
The connection URL is read from the ``FAERS_DB_URL`` environment variable so
credentials never live in source. It defaults to a local Postgres instance
holding the ``faers_agent_config`` database used to persist agent definitions.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session

# Name of the database that stores agent configurations.
DB_NAME = "faers_agent_config"


def db_url() -> URL:
    """Connection URL for the agent-config database.

    Honours ``FAERS_DB_URL`` if set; otherwise builds a local Postgres URL from
    the standard ``PG*`` env vars. Built with ``URL.create`` so passwords with
    special characters (``@``, ``:``, …) are escaped correctly rather than
    breaking URL parsing.

    If ``PGPASSWORD`` is not set, the password is left off the URL so libpq
    falls back to its own resolution — notably ``pgpass.conf`` — instead of a
    wrong hardcoded default. This matches how ``psql`` authenticates.
    """
    override = os.environ.get("FAERS_DB_URL")
    if override:
        return make_url(override)
    return URL.create(
        "postgresql+psycopg",
        username=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD"),  # None → libpq uses pgpass.conf
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5432")),
        database=DB_NAME,
    )


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: Engine | None = None


def get_engine() -> Engine:
    """Return a lazily-created, process-wide SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(db_url(), pool_pre_ping=True, future=True)
    return _engine


def get_session() -> Session:
    """Open a new ORM session bound to the shared engine."""
    return Session(get_engine(), expire_on_commit=False, future=True)
