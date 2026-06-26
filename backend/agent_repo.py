"""Persistence for agent definitions in the ``agent_config`` table.

Thin data-access layer over the :class:`~backend.models.AgentConfig` ORM model.
Returns plain dicts so callers (FastAPI routes) can serialise them directly.
"""

from __future__ import annotations

from typing import Any

from .db import db_url, get_session
from .models import AgentConfig
from .tools import fetch_records

# Columns we accept from a save payload; anything else is ignored.
_FIELDS = (
    "id",
    "name",
    "model",
    "model_source",
    "provider",
    "model_url",
    "api_key",
    "system_prompt",
    "tools",
    "knowledge_store",
    "memory_enabled",
    "human_in_loop",
)


def _to_dict(row: AgentConfig) -> dict[str, Any]:
    """Serialise an ORM row to a JSON-friendly dict."""
    return {
        "id": row.id,
        "name": row.name,
        "model": row.model,
        "model_source": row.model_source,
        "provider": row.provider,
        "model_url": row.model_url,
        # api_key is intentionally NOT returned — only a flag that one is set.
        "has_api_key": bool(row.api_key),
        "system_prompt": row.system_prompt,
        "tools": row.tools,
        "knowledge_store": row.knowledge_store,
        "memory_enabled": row.memory_enabled,
        "human_in_loop": row.human_in_loop,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def save_agent(data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new agent or update an existing one (upsert by id)."""
    fields = {k: data[k] for k in _FIELDS if k in data}
    with get_session() as session:
        row = session.get(AgentConfig, fields["id"]) if fields.get("id") else None
        if row is None:
            row = AgentConfig(**fields)
            session.add(row)
        else:
            for key, value in fields.items():
                setattr(row, key, value)
        session.commit()
        return _to_dict(row)


def list_agents() -> list[dict[str, Any]]:
    """Return all saved agents, newest first.

    Reads the ``agent_config`` table through the generic
    :func:`~backend.tools.fetch_records` DB tool.
    """
    result = fetch_records(
        db_url(),
        AgentConfig.__tablename__,
        order_by="created_at",
        descending=True,
    )
    if not result.ok:
        raise RuntimeError(f"Failed to read agents: {result.error}")
    for row in result.rows:
        # Never expose the stored credential; surface only whether one is set.
        row["has_api_key"] = bool(row.pop("api_key", ""))
        # datetimes are JSON-serialised by FastAPI; isoformat for direct callers.
        for key in ("created_at", "updated_at"):
            value = row.get(key)
            if value is not None and not isinstance(value, str):
                row[key] = value.isoformat()
    return result.rows


def delete_agent(agent_id: str) -> bool:
    """Delete an agent by id. Returns True if a row was removed."""
    with get_session() as session:
        row = session.get(AgentConfig, agent_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True
