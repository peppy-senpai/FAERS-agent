"""Persistence for projects and their uploaded files.

Thin data-access layer over the :class:`~backend.models.Project` and
:class:`~backend.models.ProjectFile` ORM models, mirroring
:mod:`backend.agent_repo`. Returns plain dicts so FastAPI routes can serialise
them directly. The uploaded *data* itself lives in each project's
``working_db_<id>`` database (see :mod:`backend.working_db`), not here — these
tables only hold the definitions and an ingest registry.
"""

from __future__ import annotations

from typing import Any

from .db import get_session
from .models import Project, ProjectFile
from . import working_db

# Columns accepted from a save payload; anything else is ignored.
_PROJECT_FIELDS = ("id", "title", "agent_id", "working_db_name")


def _project_to_dict(row: Project) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "agent_id": row.agent_id,
        "working_db_name": row.working_db_name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _file_to_dict(row: ProjectFile) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "original_filename": row.original_filename,
        "table_name": row.table_name,
        "file_format": row.file_format,
        "row_count": row.row_count,
        "status": row.status,
        "error": row.error,
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
    }


def save_project(data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new project or update an existing one (upsert by id)."""
    fields = {k: data[k] for k in _PROJECT_FIELDS if k in data}
    with get_session() as session:
        row = session.get(Project, fields["id"]) if fields.get("id") else None
        if row is None:
            row = Project(**fields)
            session.add(row)
        else:
            for key, value in fields.items():
                setattr(row, key, value)
        session.commit()
        return _project_to_dict(row)


def list_projects() -> list[dict[str, Any]]:
    """Return all projects, newest first."""
    with get_session() as session:
        rows = (
            session.query(Project).order_by(Project.created_at.desc()).all()
        )
        return [_project_to_dict(r) for r in rows]


def get_project(project_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.get(Project, project_id)
        return _project_to_dict(row) if row else None


def delete_project(project_id: str) -> bool:
    """Delete a project, its file records, and its working database.

    Returns True if the project row existed. The working database is dropped
    regardless so no orphaned data DB is left behind.
    """
    with get_session() as session:
        row = session.get(Project, project_id)
        session.query(ProjectFile).filter(
            ProjectFile.project_id == project_id
        ).delete()
        if row is not None:
            session.delete(row)
        session.commit()
        existed = row is not None
    # Drop the data DB outside the config-DB session/transaction.
    working_db.drop_working_db(project_id)
    return existed


def add_project_file(data: dict[str, Any]) -> dict[str, Any]:
    """Record an uploaded file / ingest outcome.

    Upserts by ``(project_id, table_name)`` so re-uploading into the same table
    updates the existing registry row rather than piling up duplicates.
    """
    with get_session() as session:
        row = (
            session.query(ProjectFile)
            .filter(
                ProjectFile.project_id == data["project_id"],
                ProjectFile.table_name == data["table_name"],
            )
            .one_or_none()
        )
        if row is None:
            row = ProjectFile(**data)
            session.add(row)
        else:
            for key, value in data.items():
                if key != "id":
                    setattr(row, key, value)
        session.commit()
        return _file_to_dict(row)


def list_project_files(project_id: str) -> list[dict[str, Any]]:
    with get_session() as session:
        rows = (
            session.query(ProjectFile)
            .filter(ProjectFile.project_id == project_id)
            .order_by(ProjectFile.uploaded_at.desc())
            .all()
        )
        return [_file_to_dict(r) for r in rows]
