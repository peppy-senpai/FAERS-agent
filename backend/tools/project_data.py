"""Project-data tools: read the current project's working database.

Each project's uploaded FAERS data lives in its own Postgres database,
``working_db_<project_id>`` (see :mod:`backend.working_db`). These tools let an
agent read that data.

The project is taken from the run's ``thread_id`` — which the app sets to the
project id — via the auto-injected :class:`~langchain_core.runnables.RunnableConfig`.
That parameter is filled by the runtime, not the model, so the LLM never has to
supply a project id (and can't point a query at another project's database).

Requires the agent to be invoked with
``config={"configurable": {"thread_id": project_id}}`` — the same thread_id the
chat endpoints already use.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from ..working_db import list_tables, working_db_url
from .fetch_records import fetch_records


def _project_id(config: RunnableConfig | None) -> str | None:
    """Pull the project id (thread_id) out of the run config."""
    if not config:
        return None
    return (config.get("configurable") or {}).get("thread_id")


@tool
def list_project_tables(config: RunnableConfig = None) -> dict[str, Any]:
    """List the data tables available in the current project, with row counts.

    Shows the FAERS tables uploaded into this project's database. Call this to
    discover what data is available before querying it.

    Returns:
        A result object with ``ok`` and ``tables`` (a list of ``{table,
        row_count}``), or ``error`` when ``ok`` is False.
    """
    project_id = _project_id(config)
    if not project_id:
        return {"ok": False, "error": "No project context on this run."}
    try:
        tables = list_tables(project_id)
    except Exception as exc:  # noqa: BLE001 - surface to the agent, don't crash
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "tables": tables}


@tool
def query_project_table(
    table: str,
    columns: list[str] | None = None,
    where: dict[str, Any] | None = None,
    order_by: str | None = None,
    descending: bool = False,
    limit: int = 100,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """Read rows from a table in the CURRENT project's database.

    Args:
        table: Name of the table to read (see list_project_tables).
        columns: Optional subset of column names to return. Defaults to all.
        where: Optional ``{column: value}`` equality filters, AND-ed together.
        order_by: Optional column name to sort by.
        descending: Sort descending when True (only used with order_by).
        limit: Maximum number of rows to return (default 100, capped at 5000).

    Returns:
        A result object with ``ok``, ``table``, ``rows`` (list of objects keyed
        by column), and ``error`` (message when ``ok`` is False).
    """
    project_id = _project_id(config)
    if not project_id:
        return {
            "ok": False,
            "table": table,
            "rows": [],
            "error": "No project context on this run.",
        }
    result = fetch_records(
        working_db_url(project_id),
        table,
        columns=columns,
        where=where,
        order_by=order_by,
        descending=descending,
        limit=max(1, min(limit, 5000)),
    )
    return {
        "ok": result.ok,
        "table": result.table,
        "rows": result.rows,
        "error": result.error,
    }
