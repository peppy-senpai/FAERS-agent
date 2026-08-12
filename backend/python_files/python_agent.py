"""Factory for building a runnable LangGraph agent from a saved AgentConfig.

Turns a row of the ``agent_config`` table into a ready-to-invoke agent:
  • model  — built from the provider/model/api_key (online) or local URL.
  • tools  — resolved from the saved tool ids to the real tool objects.
  • memory — an optional checkpointer when ``memory_enabled``.
  • output — optional structured response built from ``structured_output``.

This module only declares the imports needed to construct such an agent; the
build logic is added on top.
"""

from __future__ import annotations

from typing import Any

# ─── Model initialisation ─────────────────────────────────
# init_chat_model wraps any supported provider (anthropic, openai, ollama, …)
# from the provider string saved on the agent.
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

# ─── Messages ─────────────────────────────────────────────
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# ─── Tools ────────────────────────────────────────────────
from langchain_core.tools import BaseTool

# ─── Agent graph + memory ─────────────────────────────────
# create_agent is the LangChain 1.0 prebuilt agent; it replaces the now-
# deprecated langgraph.prebuilt.create_react_agent.
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

# ─── Structured output ────────────────────────────────────
# create_model builds a Pydantic schema at runtime from the agent's
# {field_name: description} spec, used as the agent's response_format.
from pydantic import BaseModel, Field, create_model

# ─── Project ──────────────────────────────────────────────
# AGENT_TOOLS is the registry of bindable tools; the per-tool objects let us
# resolve a saved tool id (which matches each tool's .name) back to the object.
from backend.tools import get_agent_tools
from backend.agent_repo import get_api_key


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


# Generated agent variables are written below by make_python_agent.py.
