"""Generic database tools.

Backend-agnostic read/write helpers that work against *any* database the
caller points at. The target database is identified by a SQLAlchemy connection
URL (``sqlite:///faers.db``, ``postgresql+psycopg://…``, ``mysql+pymysql://…``,
…), so the same functions work across backends without predefined ORM models:
each table's columns are reflected at call time.

  • :func:`insert_records` — write rows into a table.
  • :func:`fetch_records`  — read rows out of a table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from sqlalchemy import MetaData, Table, create_engine, insert, select
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import SQLAlchemyError


@dataclass
class InsertResult:
    """Outcome of an :func:`insert_records` call."""

    ok: bool
    table: str
    inserted: int
    error: str | None = None


@dataclass
class FetchResult:
    """Outcome of a :func:`fetch_records` call."""

    ok: bool
    table: str
    rows: list[dict[str, Any]] = field(default_factory=list)
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
        target = Table(
            table, metadata, schema=schema, autoload_with=engine
        )

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


def fetch_records(
    db_url: str | URL | Engine,
    table: str,
    *,
    columns: Sequence[str] | None = None,
    where: Mapping[str, Any] | None = None,
    order_by: str | None = None,
    descending: bool = False,
    limit: int | None = None,
    schema: str | None = None,
) -> FetchResult:
    """Read rows from ``table`` of the database at ``db_url``.

    The generic read counterpart to :func:`insert_records`. Reflects the
    table's columns at call time, so it works on any table in any supported
    backend without predefined ORM models.

    Args:
        db_url: A SQLAlchemy connection URL, a :class:`URL`, or an existing
            :class:`Engine`.
        table: Name of an existing table to read from.
        columns: Optional subset of column names to return. Defaults to all.
        where: Optional ``{column: value}`` equality filters, AND-ed together.
        order_by: Optional column name to sort by.
        descending: Sort descending when True (only used with ``order_by``).
        limit: Optional maximum number of rows to return.
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

        with engine.connect() as conn:
            result = conn.execute(stmt)
            rows = [dict(m) for m in result.mappings().all()]

        return FetchResult(ok=True, table=table, rows=rows)

    except SQLAlchemyError as exc:
        return FetchResult(ok=False, table=table, error=str(exc))
    finally:
        if owns_engine:
            engine.dispose()
