"""Agent-callable tools for the FAERS backend."""

from __future__ import annotations

from .db_tools import fetch_records, insert_records

__all__ = ["fetch_records", "insert_records"]
