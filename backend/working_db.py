"""Per-project working databases.

Each project owns a dedicated Postgres database ``working_db_<project_id>`` that
holds the FAERS tables uploaded into that project (one table per file). This
module provisions, inspects, and tears those databases down.

The agent-config database (``faers_agent_config``, see :mod:`backend.db`) stays
separate — it only stores agent/project *definitions*. The uploaded *data* lives
in these per-project databases.

``CREATE DATABASE`` / ``DROP DATABASE`` can't run inside a transaction, so we
connect to the maintenance ``postgres`` database with AUTOCOMMIT and issue them
directly — the same pattern used to bootstrap the config DB in
:func:`backend.init_db._ensure_database`.
"""

from __future__ import annotations

import re

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, Engine

from .db import db_url

# Postgres identifiers are max 63 bytes. Our prefix is 11 chars, leaving 52 for
# the sanitised id (a 32-char uuid hex fits comfortably).
_MAX_IDENTIFIER = 63
_PREFIX = "working_db_"


def _sanitize(project_id: str) -> str:
    """Reduce an arbitrary project id to a safe Postgres identifier fragment.

    Lowercased and restricted to ``[a-z0-9_]`` because the result is
    interpolated into DDL (database names can't be bound parameters).
    """
    cleaned = re.sub(r"[^a-z0-9_]", "_", project_id.lower())
    if not cleaned:
        raise ValueError(f"project_id {project_id!r} has no usable characters")
    return cleaned


def working_db_name(project_id: str) -> str:
    """Return the database name for a project, e.g. ``working_db_<id>``."""
    name = f"{_PREFIX}{_sanitize(project_id)}"
    return name[:_MAX_IDENTIFIER]


def working_db_url(project_id: str) -> URL:
    """SQLAlchemy URL for a project's working database."""
    return db_url().set(database=working_db_name(project_id))


def _admin_engine() -> Engine:
    """AUTOCOMMIT engine on the maintenance ``postgres`` database."""
    return create_engine(
        db_url().set(database="postgres"), isolation_level="AUTOCOMMIT"
    )


def _exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
        ).scalar()
    )


def ensure_working_db(project_id: str) -> str:
    """Create the project's working database if it doesn't exist yet.

    Called lazily on the first upload so empty projects don't litter the
    cluster. Returns the database name.
    """
    name = working_db_name(project_id)
    admin = _admin_engine()
    try:
        with admin.connect() as conn:
            if not _exists(conn, name):
                # name is sanitised above; still quote it defensively.
                conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()
    return name


def list_tables(project_id: str) -> list[dict[str, object]]:
    """List tables in a project's working database with their row counts.

    Returns an empty list if the database hasn't been created yet.
    """
    name = working_db_name(project_id)
    admin = _admin_engine()
    try:
        with admin.connect() as conn:
            if not _exists(conn, name):
                return []
    finally:
        admin.dispose()

    engine = create_engine(working_db_url(project_id))
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        out: list[dict[str, object]] = []
        with engine.connect() as conn:
            for table in sorted(tables):
                # table comes from the catalog, but quote it defensively.
                count = conn.execute(
                    text(f'SELECT count(*) FROM "{table}"')
                ).scalar()
                out.append({"table": table, "row_count": int(count or 0)})
        return out
    finally:
        engine.dispose()


def drop_working_db(project_id: str) -> bool:
    """Drop a project's working database. Returns True if one was removed.

    Postgres refuses to drop a database with live connections, so we first
    terminate any backends still attached to it.
    """
    name = working_db_name(project_id)
    admin = _admin_engine()
    try:
        with admin.connect() as conn:
            if not _exists(conn, name):
                return False
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
            return True
    finally:
        admin.dispose()
