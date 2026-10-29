"""Generated LangGraph agents.

This module is a generated artifact: :mod:`backend.python_files.make_python_agent`
and :mod:`backend.graph_compiler` write ``agent_<id> = create_agent(...)`` blocks
and ``build_agent_<id>()`` graph builders below the generated header.

All the building blocks the generated code uses (``create_agent``, ``StateGraph``,
``_chat_model``, ``_selected_tools``, ``_checkpointer``, ``_supervisor_node``, …)
come from :mod:`backend.python_files.agent_runtime`.
"""

from __future__ import annotations

from backend.python_files.agent_runtime import *  # noqa: F401,F403 (generated code uses these)
from backend.python_files.agent_runtime import (
    _chat_model,
    _checkpointer,
    _response_format,
    _selected_tools,
    _supervisor_node,
)

# Generated agent variables are written below by make_python_agent.py.
