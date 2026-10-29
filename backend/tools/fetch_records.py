"""Fetch-records database tool.

The generic read counterpart to :mod:`backend.tools.insert_records`. Reflects a
table's columns at call time, so it reads from any table in any supported
backend without predefined ORM models. The target database is identified by a
SQLAlchemy connection URL or :class:`~sqlalchemy.engine.Engine`.

Two surfaces live here:

  • :func:`fetch_records` — the plain function, callable directly from backend
    code (it takes a connection and returns a :class:`FetchResult`).
  • :data:`fetch_records_tool` — a LangGraph/LangChain ``@tool`` wrapper that
    agents bind and call. It reads from the app's configured database and
    returns a JSON-friendly dict, so it has an LLM-callable schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from langchain_core.tools import tool
from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import SQLAlchemyError


@dataclass
class FetchResult:
    """Outcome of a :func:`fetch_records` call."""

    ok: bool
    table: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def fetch_records(
    db_url: str | URL | Engine,
    table: str,
    *,
    columns: Sequence[str] | None = None,
    where: Mapping[str, Any] | None = None,
    order_by: str | None = None,
    descending: bool = False,
    limit: int | None = None,
    offset: int | None = None,
    schema: str | None = None,
) -> FetchResult:
    """Read rows from ``table`` of the database at ``db_url``.

    Args:
        db_url: A SQLAlchemy connection URL, a :class:`URL`, or an existing
            :class:`Engine`.
        table: Name of an existing table to read from.
        columns: Optional subset of column names to return. Defaults to all.
        where: Optional ``{column: value}`` equality filters, AND-ed together.
        order_by: Optional column name to sort by.
        descending: Sort descending when True (only used with ``order_by``).
        limit: Optional maximum number of rows to return.
        offset: Optional number of leading rows to skip (for pagination).
        schema: Optional schema/namespace the table lives in.

    Returns:
        A :class:`FetchResult` whose ``rows`` is a list of plain dicts keyed by
        column name. ``ok`` is False with a populated ``error`` instead of
        raising, so callers can react to failures.
    """
    owns_engine = not isinstance(db_url, Engine)
    engine: Engine = create_engine(db_url) if owns_engine else db_url

    try:
        metadata = MetaData()
        target = Table(table, metadata, schema=schema, autoload_with=engine)

        if columns:
            selected = [target.c[name] for name in columns]
            stmt = select(*selected)
        else:
            stmt = select(target)

        if where:
            for col, value in where.items():
                stmt = stmt.where(target.c[col] == value)

        if order_by:
            col = target.c[order_by]
            stmt = stmt.order_by(col.desc() if descending else col.asc())

        if limit is not None:
            stmt = stmt.limit(limit)

        if offset is not None:
            stmt = stmt.offset(offset)

        with engine.connect() as conn:
            result = conn.execute(stmt)
            rows = [dict(m) for m in result.mappings().all()]

        return FetchResult(ok=True, table=table, rows=rows)

    except SQLAlchemyError as exc:
        return FetchResult(ok=False, table=table, error=str(exc))
    finally:
        if owns_engine:
            engine.dispose()


@tool
def fetch_records_tool(
    table: str,
    columns: list[str] | None = None,
    where: dict[str, Any] | None = None,
    order_by: str | None = None,
    descending: bool = False,
    limit: int | None = None,
    db_schema: str | None = None,
) -> dict[str, Any]:
    """Read rows from a table of the application database.

    Args:
        table: Name of an existing table to read from.
        columns: Optional subset of column names to return. Defaults to all.
        where: Optional ``{column: value}`` equality filters, AND-ed together.
        order_by: Optional column name to sort by.
        descending: Sort descending when True (only used with ``order_by``).
        limit: Optional maximum number of rows to return.
        db_schema: Optional schema/namespace the table lives in.

    Returns:
        A result object with ``ok`` (whether the read succeeded), ``table``,
        ``rows`` (list of row objects keyed by column), and ``error`` (message
        when ``ok`` is False).
    """
    # Imported here so the generic helper above stays free of app-DB coupling.
    from ..db import db_url

    result = fetch_records(
        db_url(),
        table,
        columns=columns,
        where=where,
        order_by=order_by,
        descending=descending,
        limit=limit,
        schema=db_schema,
    )
    return {
        "ok": result.ok,
        "table": result.table,
        "rows": result.rows,
        "error": result.error,
    }
