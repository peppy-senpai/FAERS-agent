"""Insert-records database tool.

Backend-agnostic write helper that works against *any* database the caller
points at. The target database is identified by a SQLAlchemy connection URL
(``sqlite:///faers.db``, ``postgresql+psycopg://…``, ``mysql+pymysql://…``, …),
so the same function works across backends without predefined ORM models: the
table's columns are reflected at call time.

Two surfaces live here:

  • :func:`insert_records` — the plain function, callable directly from backend
    code (it takes a connection and returns an :class:`InsertResult`).
  • :data:`insert_records_tool` — a LangGraph/LangChain ``@tool`` wrapper that
    agents bind and call. It targets the app's configured database and returns
    a JSON-friendly dict, so it has an LLM-callable schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from langchain_core.tools import tool
from sqlalchemy import MetaData, Table, create_engine, insert
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import SQLAlchemyError


@dataclass
class InsertResult:
    """Outcome of an :func:`insert_records` call."""

    ok: bool
    table: str
    inserted: int
    error: str | None = None


def insert_records(
    db_url: str | URL | Engine,
    table: str,
    records: Sequence[Mapping[str, Any]],
    *,
    schema: str | None = None,
    drop_unknown_columns: bool = True,
) -> InsertResult:
    """Insert ``records`` into ``table`` of the database at ``db_url``.

    Args:
        db_url: A SQLAlchemy connection URL (e.g. ``"sqlite:///faers.db"`` or
            ``"postgresql+psycopg://user:pw@host/db"``), or an already-built
            :class:`~sqlalchemy.engine.Engine`. The URL's dialect decides which
            backend is targeted, so this works for "any db inputted".
        table: Name of an existing table to insert into.
        records: A sequence of mappings (dicts), one per row, keyed by column
            name. All rows are inserted in a single transaction — either all
            succeed or none do.
        schema: Optional schema/namespace the table lives in.
        drop_unknown_columns: When True (default), keys not present in the
            reflected table are silently dropped from each row, so loosely
            shaped agent output doesn't fail the whole insert. When False, an
            unknown key surfaces as a database error.

    Returns:
        An :class:`InsertResult`. ``ok`` is False with a populated ``error``
        instead of raising, so an agent can read the failure and react.

    Notes:
        The table must already exist; this function reflects its columns rather
        than creating it, because a safe cross-backend ``CREATE TABLE`` needs a
        column schema the caller hasn't supplied.
    """
    if not records:
        return InsertResult(ok=True, table=table, inserted=0)

    # Accept either a URL we own (and must dispose) or a caller-owned engine.
    owns_engine = not isinstance(db_url, Engine)
    engine: Engine = create_engine(db_url) if owns_engine else db_url

    try:
        metadata = MetaData()
        target = Table(table, metadata, schema=schema, autoload_with=engine)

        rows: list[Mapping[str, Any]] = list(records)
        if drop_unknown_columns:
            cols = set(target.columns.keys())
            rows = [{k: v for k, v in row.items() if k in cols} for row in rows]

        # Single transaction: begin() commits on success, rolls back on error.
        with engine.begin() as conn:
            result = conn.execute(insert(target), rows)

        # rowcount is unreliable on some drivers for executemany; fall back to
        # the number of rows we asked to insert.
        inserted = result.rowcount if result.rowcount and result.rowcount > 0 else len(rows)
        return InsertResult(ok=True, table=table, inserted=inserted)

    except SQLAlchemyError as exc:
        return InsertResult(ok=False, table=table, inserted=0, error=str(exc))
    finally:
        if owns_engine:
            engine.dispose()


@tool
def insert_records_tool(
    table: str,
    records: list[dict[str, Any]],
    db_schema: str | None = None,
) -> dict[str, Any]:
    """Insert rows into a table of the application database.

    Args:
        table: Name of an existing table to insert into.
        records: A list of rows to insert; each row is an object keyed by column
            name. Keys that don't match a column are ignored.
        db_schema: Optional schema/namespace the table lives in.

    Returns:
        A result object with ``ok`` (whether the insert succeeded), ``table``,
        ``inserted`` (row count), and ``error`` (message when ``ok`` is False).
    """
    # Imported here so the generic helper above stays free of app-DB coupling.
    from ..db import db_url

    result = insert_records(db_url(), table, records, schema=db_schema)
    return {
        "ok": result.ok,
        "table": result.table,
        "inserted": result.inserted,
        "error": result.error,
    }
