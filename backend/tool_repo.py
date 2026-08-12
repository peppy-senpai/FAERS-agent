"""Persistence for uploaded custom tools.

Thin data-access layer over :class:`~backend.models.CustomTool`, mirroring
:mod:`backend.agent_repo`. The executable code lives on disk under
``FAERS_TOOLS_DIR`` (see :mod:`backend.tools.custom_loader`); these rows are the
registry that lets the UI list custom tools and survive restarts.
"""

from __future__ import annotations

from typing import Any

from .db import get_session
from .models import CustomTool


def _to_dict(row: CustomTool) -> dict[str, Any]:
    return {
        "name": row.name,
        "description": row.description,
        "source_filename": row.source_filename,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def upsert_tool(name: str, description: str, source_filename: str) -> dict[str, Any]:
    """Insert or update a custom-tool registry row (keyed by tool name)."""
    with get_session() as session:
        row = session.get(CustomTool, name)
        if row is None:
            row = CustomTool(
                name=name,
                description=description,
                source_filename=source_filename,
            )
            session.add(row)
        else:
            row.description = description
            row.source_filename = source_filename
        session.commit()
        return _to_dict(row)


def list_tools() -> list[dict[str, Any]]:
    """Return all custom tools, newest first."""
    with get_session() as session:
        rows = (
            session.query(CustomTool).order_by(CustomTool.created_at.desc()).all()
        )
        return [_to_dict(r) for r in rows]


def get_tool(name: str) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.get(CustomTool, name)
        return _to_dict(row) if row else None


def delete_tool(name: str) -> bool:
    """Delete a custom-tool row. Returns True if one existed."""
    with get_session() as session:
        row = session.get(CustomTool, name)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True
