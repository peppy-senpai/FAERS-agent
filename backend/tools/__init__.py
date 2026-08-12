"""Agent-callable tools for the FAERS backend.

Each tool lives in its own module. Every module exposes a plain function for
direct backend use and a LangGraph/LangChain ``@tool`` wrapper (``*_tool``) that
agents bind:

  • :mod:`backend.tools.insert_records` — write rows into a table.
  • :mod:`backend.tools.fetch_records`  — read rows out of a table.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from .custom_loader import custom_tools
from .fetch_records import FetchResult, fetch_records, fetch_records_tool
from .insert_records import InsertResult, insert_records, insert_records_tool
from .project_data import list_project_tables, query_project_table

# Built-in tools, always available. Custom (uploaded) tools are added on top by
# get_agent_tools() at call time.
AGENT_TOOLS = [
    insert_records_tool,
    fetch_records_tool,
    list_project_tables,
    query_project_table,
]

# Names reserved by built-ins; a custom upload can't shadow these.
BUILTIN_TOOL_NAMES = {tool.name for tool in AGENT_TOOLS}


def get_agent_tools() -> list[BaseTool]:
    """All bindable tools: built-ins plus any uploaded custom tools.

    Resolved dynamically so tools uploaded at runtime are visible without a
    restart. The agent factory resolves saved tool ids against this list.
    """
    return [*AGENT_TOOLS, *custom_tools()]


__all__ = [
    "AGENT_TOOLS",
    "BUILTIN_TOOL_NAMES",
    "FetchResult",
    "InsertResult",
    "custom_tools",
    "fetch_records",
    "fetch_records_tool",
    "get_agent_tools",
    "insert_records",
    "insert_records_tool",
    "list_project_tables",
    "query_project_table",
]
