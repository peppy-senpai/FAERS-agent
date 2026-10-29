"""ORM models persisted in the ``faers_agent_config`` database."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class AgentConfig(Base):
    """A saved agent definition — one row per agent built in the UI.

    Mirrors the frontend ``state.Agent`` model. List/nested fields (``tools``,
    ``knowledge_store``) are stored as JSONB so they're queryable in Postgres
    while still round-tripping cleanly to/from the Pydantic models.
    """

    __tablename__ = "agent_config"

    # Reuse the agent's uuid hex from the frontend as the primary key.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    model_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="local"
    )  # local | api
    provider: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )  # langchain init_chat_model provider, for online APIs
    model_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Optional structured-output spec: {field_name: description}. NULL = free text.
    structured_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Optional visual node-graph spec ({nodes, edges}) when the agent was built
    # in the graph canvas. NULL for form-built agents.
    graph: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tools: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    knowledge_store: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    memory_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    human_in_loop: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<AgentConfig id={self.id!r} name={self.name!r} model={self.model!r}>"


class Project(Base):
    """A persisted project — one row per project created in the UI.

    Persisting projects (they were previously session-only) gives each a stable
    id, which in turn owns a dedicated ``working_db_<id>`` Postgres database
    holding the FAERS data uploaded into that project. Without persistence the
    session-generated id would change each run and orphan those databases.
    """

    __tablename__ = "project"

    # Reuse the project's uuid hex from the frontend as the primary key.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New project")
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Name of this project's working database; set once data is first uploaded.
    working_db_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Project id={self.id!r} title={self.title!r}>"


class ProjectFile(Base):
    """One uploaded file, loaded as a table in a project's working database.

    Registry/audit of what has been ingested: which file became which table,
    how many rows landed, and whether it succeeded. The bytes themselves live in
    the working database as a table, not here.
    """

    __tablename__ = "project_file"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    table_name: Mapped[str] = mapped_column(String(63), nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")  # ok | error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<ProjectFile id={self.id!r} project_id={self.project_id!r} "
            f"table={self.table_name!r} rows={self.row_count}>"
        )


class CustomTool(Base):
    """A user-uploaded ``@tool`` file registered as an agent-callable tool.

    The row is the persistence/registry record; the executable code lives in the
    ``.py`` file at ``source_filename`` under ``FAERS_TOOLS_DIR``. ``name`` is the
    tool's ``.name`` — the id agents reference, so it's the primary key.
    """

    __tablename__ = "custom_tool"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Filename (not full path) of the stored source under FAERS_TOOLS_DIR.
    source_filename: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<CustomTool name={self.name!r} file={self.source_filename!r}>"
