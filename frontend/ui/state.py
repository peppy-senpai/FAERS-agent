"""Application state, backed by st.session_state.

Python port of frontend/src/store/appStore.ts. Where the React app used a
persisted Zustand store, we use Streamlit's per-session state. Projects, agents
and tools live for the life of the browser session.
"""

from __future__ import annotations

import time
import uuid

import requests
import streamlit as st
from pydantic import BaseModel, Field

from . import api

# ─── Domain types ─────────────────────────────────────────


class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = Field(default_factory=time.time)


class Project(BaseModel):
    title: str = "New project"
    agent_id: str | None = None
    # Name of this project's working database, once data has been uploaded.
    working_db_name: str = ""
    messages: list[Message] = Field(default_factory=list)
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = Field(default_factory=time.time)


class KnowledgeStore(BaseModel):
    """Vector storage configuration for an agent's knowledge base."""

    store_type: str = "none"  # none | local | cloud
    location: str = ""  # local path or cloud connection URL
    files: list[str] = Field(default_factory=list)  # uploaded source file names


class Agent(BaseModel):
    name: str
    model: str
    model_source: str = "local"  # local | api
    provider: str = ""  # langchain init_chat_model provider, when model_source == "api"
    model_url: str = ""  # base URL of the online API, when model_source == "api"
    api_key: str = ""  # credential for the online API
    system_prompt: str
    # Optional structured-output spec: {field_name: value_description}. None when
    # the agent returns free-form text.
    structured_output: dict | None = None
    tools: list[str] = Field(default_factory=list)
    knowledge_store: KnowledgeStore = Field(default_factory=KnowledgeStore)
    memory_enabled: bool = True
    human_in_loop: bool = False
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)


class Tool(BaseModel):
    name: str
    description: str  # short one-liner, shown in lists and the selection chip
    # Full multi-level description (mirrors the tool function's docstring) shown
    # on hover in the agent builder. Empty for user-added tools.
    help: str = ""
    builtin: bool = False
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)


# ─── Seed data ────────────────────────────────────────────

MODELS = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]

# Chat-model provider wrappers LangChain's ``init_chat_model`` supports (which
# LangGraph builds on). Shown in the Agent Builder when wiring an online API.
MODEL_PROVIDERS = [
    "openai",
    "anthropic",
    "azure_openai",
    "azure_ai",
    "google_vertexai",
    "google_genai",
    "google_anthropic_vertex",
    "bedrock",
    "bedrock_converse",
    "cohere",
    "fireworks",
    "together",
    "mistralai",
    "huggingface",
    "groq",
    "ollama",
    "deepseek",
    "ibm",
    "nvidia",
    "xai",
    "perplexity",
]


def _builtin_tools() -> list[Tool]:
    """Built-in tools the agents can call, backed by real implementations.

    Ids match the LangGraph tool ``.name`` in ``backend.tools.AGENT_TOOLS`` so
    the agent runtime can resolve a saved tool id to its tool object.
    """
    return [
        # Generic database tools (backend/tools/*). Ids match the LangGraph tool
        # ``.name`` so the agent runtime can resolve them to backend.tools.AGENT_TOOLS.
        Tool(
            id="fetch_records_tool",
            name="Fetch Records",
            description="Read rows from a table in the application database.",
            help=(
                "Read rows from a table of the application database.\n\n"
                "Args:\n"
                "  table: Name of an existing table to read from.\n"
                "  columns: Optional subset of column names to return (default all).\n"
                "  where: Optional {column: value} equality filters, AND-ed together.\n"
                "  order_by: Optional column name to sort by.\n"
                "  descending: Sort descending when True (only with order_by).\n"
                "  limit: Optional maximum number of rows to return.\n"
                "  db_schema: Optional schema/namespace the table lives in.\n\n"
                "Returns: {ok, table, rows, error}."
            ),
            builtin=True,
        ),
        Tool(
            id="insert_records_tool",
            name="Insert Records",
            description="Insert rows into a table in the application database.",
            help=(
                "Insert rows into a table of the application database.\n\n"
                "Args:\n"
                "  table: Name of an existing table to insert into.\n"
                "  records: List of rows to insert; each row is an object keyed by\n"
                "    column name. Keys that don't match a column are ignored.\n"
                "  db_schema: Optional schema/namespace the table lives in.\n\n"
                "Returns: {ok, table, inserted, error}."
            ),
            builtin=True,
        ),
        # Project-data tools: read the current project's working database. The
        # project is taken from the run context, so there's no project-id arg.
        Tool(
            id="list_project_tables",
            name="List Project Tables",
            description="List the data tables uploaded into the current project, with row counts.",
            help=(
                "List the data tables available in the current project, with row\n"
                "counts. Use this to discover what FAERS data is available before\n"
                "querying it.\n\n"
                "Returns: {ok, tables: [{table, row_count}], error}."
            ),
            builtin=True,
        ),
        Tool(
            id="query_project_table",
            name="Query Project Table",
            description="Read rows from a table in the current project's database.",
            help=(
                "Read rows from a table in the CURRENT project's database.\n\n"
                "Args:\n"
                "  table: Name of the table to read (see List Project Tables).\n"
                "  columns: Optional subset of columns to return (default all).\n"
                "  where: Optional {column: value} equality filters, AND-ed.\n"
                "  order_by: Optional column to sort by.\n"
                "  descending: Sort descending when True (only with order_by).\n"
                "  limit: Max rows to return (default 100, capped at 5000).\n\n"
                "Returns: {ok, table, rows, error}."
            ),
            builtin=True,
        ),
    ]


def _default_agent() -> Agent:
    return Agent(
        id="default-faers-agent",
        name="FAERS Safety Analyst",
        model="claude-opus-4-8",
        system_prompt=(
            "You are a pharmacovigilance analyst. Use the FAERS tools to answer "
            "questions about post-marketing drug safety signals. Always cite the "
            "counts behind any disproportionality finding."
        ),
        tools=[t.id for t in _builtin_tools()],
        memory_enabled=True,
        human_in_loop=False,
    )


# ─── Initialisation ───────────────────────────────────────


def _load_projects() -> list["Project"]:
    """Load persisted projects from the backend; empty list if it's unreachable.

    Message history isn't persisted yet, so reloaded projects start with an
    empty transcript.
    """
    try:
        rows = api.list_projects()
    except requests.RequestException:
        return []
    return [
        Project(
            id=r["id"],
            title=r.get("title") or "New project",
            agent_id=r.get("agent_id"),
            working_db_name=r.get("working_db_name") or "",
        )
        for r in rows
    ]


def _custom_tools_from_backend() -> list["Tool"]:
    """Fetch uploaded custom tools from the backend; empty if unreachable."""
    try:
        rows = api.list_tools()
    except requests.RequestException:
        return []
    return [
        Tool(
            id=r["id"],
            name=r["name"],
            description=r.get("description", ""),
            builtin=False,
        )
        for r in rows
        if not r.get("builtin")
    ]


def refresh_tools() -> None:
    """Rebuild the tool list from built-ins + backend custom tools."""
    st.session_state.tools = _builtin_tools() + _custom_tools_from_backend()


def init_state() -> None:
    """Seed st.session_state once per session."""
    ss = st.session_state
    if "initialized" in ss:
        return
    ss.projects = _load_projects()  # list[Project], persisted across sessions
    ss.agents = [_default_agent()]
    ss.tools = _builtin_tools() + _custom_tools_from_backend()
    ss.active_project_id = None
    ss.view = "projects"  # projects | agents | tools | settings
    ss.theme = "light"
    ss.initialized = True


# ─── Project actions ──────────────────────────────────────


def create_project(agent_id: str | None = None) -> str:
    ss = st.session_state
    default_agent = ss.agents[0].id if ss.agents else None
    project = Project(agent_id=agent_id or default_agent)
    ss.projects.insert(0, project)
    ss.active_project_id = project.id
    # Persist best-effort; degrade to session-only if the backend is down.
    try:
        api.create_project(project.id, project.title, project.agent_id)
    except requests.RequestException:
        pass
    return project.id


def delete_project(project_id: str) -> None:
    ss = st.session_state
    ss.projects = [p for p in ss.projects if p.id != project_id]
    if ss.active_project_id == project_id:
        ss.active_project_id = ss.projects[0].id if ss.projects else None
    try:
        api.delete_project(project_id)
    except requests.RequestException:
        pass


def set_active_project(project_id: str | None) -> None:
    st.session_state.active_project_id = project_id


def get_project(project_id: str | None) -> Project | None:
    if project_id is None:
        return None
    return next((p for p in st.session_state.projects if p.id == project_id), None)


def get_agent(agent_id: str | None) -> Agent | None:
    agents = st.session_state.agents
    found = next((a for a in agents if a.id == agent_id), None)
    return found or (agents[0] if agents else None)


def add_message(project_id: str, role: str, content: str) -> str:
    """Append a message; the first user message becomes the project title."""
    project = get_project(project_id)
    if project is None:
        return ""
    if not project.messages and role == "user":
        project.title = content[:40]
        # Persist the derived title best-effort so it survives a reload.
        try:
            api.create_project(project.id, project.title, project.agent_id)
        except requests.RequestException:
            pass
    msg = Message(role=role, content=content)
    project.messages.append(msg)
    return msg.id


def append_to_message(project_id: str, message_id: str, chunk: str) -> None:
    project = get_project(project_id)
    if project is None:
        return
    for m in project.messages:
        if m.id == message_id:
            m.content += chunk
            return


# ─── Agent actions ────────────────────────────────────────


def add_agent(agent: Agent) -> str:
    st.session_state.agents.append(agent)
    return agent.id


def delete_agent(agent_id: str) -> None:
    ss = st.session_state
    if len(ss.agents) <= 1:
        return  # keep at least one agent
    ss.agents = [a for a in ss.agents if a.id != agent_id]


# ─── Tool actions ─────────────────────────────────────────


def add_tool(name: str, description: str) -> str:
    tool = Tool(name=name, description=description)
    st.session_state.tools.append(tool)
    return tool.id


def delete_tool(tool_id: str) -> None:
    ss = st.session_state
    tool = next((t for t in ss.tools if t.id == tool_id), None)
    # Custom tools are backed by the server; remove there too (best-effort).
    if tool is not None and not tool.builtin:
        try:
            api.delete_tool(tool.name)
        except requests.RequestException:
            pass
    ss.tools = [t for t in ss.tools if t.id != tool_id]
