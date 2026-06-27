"""ORM models persisted in the ``faers_agent_config`` database."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
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
