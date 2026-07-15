"""Agent-callable tools for the FAERS backend.

Each tool lives in its own module. Every module exposes a plain function for
direct backend use and a LangGraph/LangChain ``@tool`` wrapper (``*_tool``) that
agents bind:

  • :mod:`backend.tools.insert_records` — write rows into a table.
  • :mod:`backend.tools.fetch_records`  — read rows out of a table.
"""

from __future__ import annotations

from .fetch_records import FetchResult, fetch_records, fetch_records_tool
from .insert_records import InsertResult, insert_records, insert_records_tool

# Tools agents can bind, in one place for registration.
AGENT_TOOLS = [insert_records_tool, fetch_records_tool]

__all__ = [
    "AGENT_TOOLS",
    "FetchResult",
    "InsertResult",
    "fetch_records",
    "fetch_records_tool",
    "insert_records",
    "insert_records_tool",
]
