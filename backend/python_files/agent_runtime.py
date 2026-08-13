"""Runtime helpers for building runnable LangGraph agents from saved configs.

These are the hand-written building blocks that generated code (in
``python_agent.py``, written by :mod:`backend.python_files.make_python_agent`
and :mod:`backend.graph_compiler`) composes:

  • model  — :func:`_chat_model` from the provider/model/api_key (online) or URL.
  • tools  — :func:`_selected_tools` resolves saved ids to real tool objects.
  • memory — :func:`_checkpointer`, an optional checkpointer.
  • output — :func:`_response_format`, an optional structured response schema.
  • orchestration — :func:`_supervisor_node` for multi-agent graphs.

They live here (separate from the generated ``python_agent.py``) so a graph
builder can be validated/executed without running unrelated generated top-level
code.
"""

from __future__ import annotations

from typing import Any

# init_chat_model wraps any supported provider (anthropic, openai, ollama, …).
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

# create_agent is the LangChain 1.0 prebuilt agent; StateGraph wires several of
# them into an orchestrated graph.
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command

# create_model builds a Pydantic schema at runtime from the agent's
# {field_name: description} spec, used as the agent's response_format.
from pydantic import BaseModel, Field, create_model

from backend.tools import get_agent_tools
from backend.agent_repo import get_api_key

# Names generated code relies on (so ``from .agent_runtime import *`` exposes
# them in python_agent.py's namespace).
__all__ = [
    "AIMessage",
    "HumanMessage",
    "SystemMessage",
    "BaseChatModel",
    "BaseTool",
    "create_agent",
    "InMemorySaver",
    "StateGraph",
    "START",
    "END",
    "MessagesState",
    "Command",
    "BaseModel",
    "Field",
    "create_model",
    "get_agent_tools",
    "get_api_key",
    "_selected_tools",
    "_schema_name",
    "_response_format",
    "_chat_model",
    "_checkpointer",
    "_supervisor_node",
]


def _selected_tools(tool_ids: list[str]) -> list[BaseTool]:
    """Resolve saved tool ids to the registered LangChain tool objects.

    Draws from ``get_agent_tools()`` so uploaded custom tools resolve alongside
    the built-ins.
    """
    selected = set(tool_ids)
    return [tool for tool in get_agent_tools() if tool.name in selected]


def _schema_name(agent_id: str) -> str:
    safe_id = "".join(char if char.isalnum() else "_" for char in agent_id)
    return f"Agent{safe_id}Response"


def _response_format(
    agent_id: str,
    structured_output: dict[str, str] | None,
) -> type[BaseModel] | None:
    """Build a runtime Pydantic response schema from the saved field spec."""
    if not structured_output:
        return None

    fields: dict[str, tuple[type[str], Any]] = {
        name: (str, Field(description=description))
        for name, description in structured_output.items()
    }
    return create_model(_schema_name(agent_id), **fields)


def _chat_model(
    *,
    agent_id: str,
    model: str,
    model_source: str,
    provider: str,
    model_url: str,
) -> BaseChatModel:
    """Create the chat model declared by the saved agent config."""
    kwargs: dict[str, Any] = {}
    if provider:
        kwargs["model_provider"] = provider
    if model_url:
        kwargs["base_url"] = model_url
    if model_source == "api":
        api_key = get_api_key(agent_id)
        if api_key:
            kwargs["api_key"] = api_key
    return init_chat_model(model, **kwargs)


def _checkpointer(memory_enabled: bool) -> InMemorySaver | None:
    return InMemorySaver() if memory_enabled else None


# ─── Supervisor orchestration helper ──────────────────────
# Used by generated graphs with a Supervisor block: the supervisor asks its
# model which worker should act next (or FINISH) and routes there via a
# LangGraph ``Command``. Workers edge back to the supervisor, so control loops
# until the supervisor decides to finish.


def _supervisor_node(
    *,
    model: BaseChatModel,
    system_prompt: str,
    workers: list[str],
):
    """Build a supervisor node that routes among ``workers`` (or ends)."""
    options = workers + ["FINISH"]
    instructions = (
        f"{system_prompt}\n\n"
        f"You coordinate these workers: {', '.join(workers)}.\n"
        "Given the conversation so far, reply with ONLY the name of the worker "
        "that should act next, or FINISH if the task is complete. "
        f"Respond with exactly one of: {', '.join(options)}."
    )

    def supervise(state: MessagesState) -> Command:
        messages = [SystemMessage(content=instructions), *state["messages"]]
        reply = model.invoke(messages)
        choice = (reply.text() if hasattr(reply, "text") else str(reply.content)).strip()
        goto = next((w for w in workers if w.lower() in choice.lower()), "FINISH")
        return Command(goto=END if goto == "FINISH" else goto)

    return supervise
