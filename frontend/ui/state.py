"""Application state, backed by st.session_state.

Python port of frontend/src/store/appStore.ts. Where the React app used a
persisted Zustand store, we use Streamlit's per-session state. Chats, agents
and tools live for the life of the browser session.
"""

from __future__ import annotations

import time
import uuid

import streamlit as st
from pydantic import BaseModel, Field

# ─── Domain types ─────────────────────────────────────────


class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = Field(default_factory=time.time)


class Chat(BaseModel):
    title: str = "New chat"
    agent_id: str | None = None
    messages: list[Message] = Field(default_factory=list)
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = Field(default_factory=time.time)


class Agent(BaseModel):
    name: str
    model: str
    system_prompt: str
    tools: list[str] = Field(default_factory=list)
    memory_enabled: bool = True
    human_in_loop: bool = False
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)


class Tool(BaseModel):
    name: str
    description: str
    builtin: bool = False
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)


# ─── Seed data ────────────────────────────────────────────

MODELS = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]


def _builtin_tools() -> list[Tool]:
    """FAERS-oriented tools the agents can call.

    These mirror the backend tool layer exposed over the local FAERS database.
    Stable ids match the original frontend so backend calls line up.
    """
    return [
        Tool(
            id="search_adverse_events",
            name="Search Adverse Events",
            description="Find adverse event reports for a given drug in FAERS.",
            builtin=True,
        ),
        Tool(
            id="disproportionality",
            name="Disproportionality (ROR/PRR)",
            description="Compute ROR, PRR and chi-square for a drug-event pair.",
            builtin=True,
        ),
        Tool(
            id="top_events_for_drug",
            name="Top Events for Drug",
            description="List the most frequently reported reactions for a drug.",
            builtin=True,
        ),
        Tool(
            id="report_counts",
            name="Report Counts",
            description="Aggregate report counts by age, sex, geography, or quarter.",
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


def init_state() -> None:
    """Seed st.session_state once per session."""
    ss = st.session_state
    if "initialized" in ss:
        return
    ss.chats = []  # list[Chat]
    ss.agents = [_default_agent()]
    ss.tools = _builtin_tools()
    ss.active_chat_id = None
    ss.view = "chat"  # chat | agents | tools | settings
    ss.theme = "light"
    ss.initialized = True


# ─── Chat actions ─────────────────────────────────────────


def create_chat(agent_id: str | None = None) -> str:
    ss = st.session_state
    default_agent = ss.agents[0].id if ss.agents else None
    chat = Chat(agent_id=agent_id or default_agent)
    ss.chats.insert(0, chat)
    ss.active_chat_id = chat.id
    return chat.id


def delete_chat(chat_id: str) -> None:
    ss = st.session_state
    ss.chats = [c for c in ss.chats if c.id != chat_id]
    if ss.active_chat_id == chat_id:
        ss.active_chat_id = ss.chats[0].id if ss.chats else None


def set_active_chat(chat_id: str | None) -> None:
    st.session_state.active_chat_id = chat_id


def get_chat(chat_id: str | None) -> Chat | None:
    if chat_id is None:
        return None
    return next((c for c in st.session_state.chats if c.id == chat_id), None)


def get_agent(agent_id: str | None) -> Agent | None:
    agents = st.session_state.agents
    found = next((a for a in agents if a.id == agent_id), None)
    return found or (agents[0] if agents else None)


def add_message(chat_id: str, role: str, content: str) -> str:
    """Append a message; the first user message becomes the chat title."""
    chat = get_chat(chat_id)
    if chat is None:
        return ""
    if not chat.messages and role == "user":
        chat.title = content[:40]
    msg = Message(role=role, content=content)
    chat.messages.append(msg)
    return msg.id


def append_to_message(chat_id: str, message_id: str, chunk: str) -> None:
    chat = get_chat(chat_id)
    if chat is None:
        return
    for m in chat.messages:
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
    ss.tools = [t for t in ss.tools if t.id != tool_id]
