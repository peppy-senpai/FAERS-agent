"""Initialise the agent-config database.

Idempotent bootstrap that:
  1. Creates the ``faers_agent_config`` database if it doesn't exist.
  2. Creates the ``agent_config`` table (and any other ORM tables).

Run once after setting up Postgres::

    python -m backend.init_db

Credentials come from the same env vars as :mod:`backend.db` (``FAERS_DB_URL``
or ``PGPASSWORD``), so nothing secret is hardcoded here.
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from . import models  # noqa: F401  (registers AgentConfig on Base.metadata)
from .db import DB_NAME, Base, db_url, get_engine


def _ensure_database() -> None:
    """Create the target database if it isn't there yet.

    CREATE DATABASE can't run inside a transaction, so we connect to the
    maintenance ``postgres`` database with AUTOCOMMIT and issue it directly.
    """
    admin_url = db_url().set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": DB_NAME},
            ).scalar()
            if exists:
                print(f"Database {DB_NAME!r} already exists.")
            else:
                # Identifier can't be parameterised; DB_NAME is a fixed constant.
                conn.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
                print(f"Created database {DB_NAME!r}.")
    finally:
        admin_engine.dispose()


def _create_tables() -> None:
    """Create all ORM tables in the target database (no-op if present)."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("Tables ready:", ", ".join(sorted(Base.metadata.tables)))


def _add_missing_columns() -> None:
    """Add columns present on the ORM models but missing from existing tables.

    ``create_all`` only creates whole tables; it never alters one that already
    exists. This lightweight reconcile keeps a pre-existing ``agent_config``
    table in sync as new columns are added to the models. (For anything beyond
    additive columns, use a real migration tool such as Alembic.)
    """
    engine = get_engine()
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            if not inspector.has_table(table.name, schema=table.schema):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = column.type.compile(dialect=engine.dialect)
                default = "" if column.nullable else " NOT NULL DEFAULT ''"
                conn.execute(
                    text(
                        f'ALTER TABLE {table.name} '
                        f'ADD COLUMN IF NOT EXISTS {column.name} {ddl}{default}'
                    )
                )
                print(f"Added column {table.name}.{column.name} ({ddl}).")


def main() -> None:
    _ensure_database()
    _create_tables()
    _add_missing_columns()
    print("Done.")


if __name__ == "__main__":
    main()
