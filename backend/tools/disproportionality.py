"""Disproportionality analysis tools over the current project's FAERS data.

The Reporting Odds Ratio (ROR) is the standard pharmacovigilance signal metric.
It's computed from a 2x2 report-count table for a drug / adverse-event pair:

                 event      no-event
    drug           a           b
    other drugs    c           d

    ROR = (a*d) / (b*c)

This tool builds that table by counting reports (distinct case ids) in a project
table, then returns the ROR with a 95% confidence interval and a signal flag. The
project comes from the run's ``thread_id`` via the injected ``RunnableConfig`` —
same pattern as :mod:`backend.tools.project_data`.
"""

from __future__ import annotations

import math
import re
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from ..working_db import working_db_url


def _project_id(config: RunnableConfig | None) -> str | None:
    if not config:
        return None
    return (config.get("configurable") or {}).get("thread_id")


def _ident(name: str) -> str:
    """Validate and quote a SQL identifier (table/column can't be bound)."""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        raise ValueError(f"Invalid identifier: {name!r}")
    return f'"{name}"'


def _ror(a: int, b: int, c: int, d: int) -> dict[str, Any]:
    """ROR point estimate + 95% CI, with Haldane correction on any zero cell."""
    corrected = min(a, b, c, d) == 0
    aa, bb, cc, dd = (a + 0.5, b + 0.5, c + 0.5, d + 0.5) if corrected else (a, b, c, d)
    ror = (aa * dd) / (bb * cc)
    se = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / dd)
    lower = math.exp(math.log(ror) - 1.96 * se)
    upper = math.exp(math.log(ror) + 1.96 * se)
    return {
        "ror": round(ror, 3),
        "ci_lower": round(lower, 3),
        "ci_upper": round(upper, 3),
        "continuity_correction": corrected,
        # Common signal rule: CI lower bound above 1 with at least 3 cases.
        "signal": lower > 1.0 and a >= 3,
    }


@tool
def reporting_odds_ratio(
    drug: str,
    event: str,
    table: str,
    drug_col: str = "drugname",
    event_col: str = "pt",
    id_col: str = "primaryid",
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """Compute the Reporting Odds Ratio (ROR) for a drug / adverse-event pair.

    Builds the 2x2 report-count table from a table in the CURRENT project's
    database and returns the ROR with a 95% confidence interval and a signal
    flag. Matching on drug/event is case-insensitive.

    Args:
        drug: Drug name to test (matched against ``drug_col``).
        event: Adverse-event term to test (matched against ``event_col``).
        table: Table holding one row per report/drug/reaction (e.g. the combined
            FAERS table produced by ingest_faers_quarter).
        drug_col: Column with the drug name. Default ``drugname``.
        event_col: Column with the reaction/event term. Default ``pt``.
        id_col: Column identifying a unique report/case. Default ``primaryid``.

    Returns:
        ``{ok, drug, event, table, counts: {a, b, c, d, n}, ror, ci_lower,
        ci_upper, signal, continuity_correction, error}``. Counts are distinct
        report ids. On failure ``ok`` is False with an ``error`` message.
    """
    project_id = _project_id(config)
    if not project_id:
        return {"ok": False, "error": "No project context on this run."}

    try:
        t, dcol, ecol, idc = (
            _ident(table),
            _ident(drug_col),
            _ident(event_col),
            _ident(id_col),
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    engine = create_engine(working_db_url(project_id))
    try:
        with engine.connect() as conn:
            n = conn.execute(text(f"SELECT COUNT(DISTINCT {idc}) FROM {t}")).scalar()
            n_drug = conn.execute(
                text(f"SELECT COUNT(DISTINCT {idc}) FROM {t} WHERE upper({dcol}) = upper(:v)"),
                {"v": drug},
            ).scalar()
            n_event = conn.execute(
                text(f"SELECT COUNT(DISTINCT {idc}) FROM {t} WHERE upper({ecol}) = upper(:v)"),
                {"v": event},
            ).scalar()
            a = conn.execute(
                text(
                    f"SELECT COUNT(DISTINCT {idc}) FROM {t} "
                    f"WHERE upper({dcol}) = upper(:d) AND upper({ecol}) = upper(:e)"
                ),
                {"d": drug, "e": event},
            ).scalar()
    except SQLAlchemyError as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        engine.dispose()

    n, n_drug, n_event, a = int(n or 0), int(n_drug or 0), int(n_event or 0), int(a or 0)
    b = n_drug - a
    c = n_event - a
    d = n - a - b - c
    if min(a, b, c, d) < 0:
        return {"ok": False, "error": "Inconsistent counts — check the column names."}

    result: dict[str, Any] = {
        "ok": True,
        "drug": drug,
        "event": event,
        "table": table,
        "counts": {"a": a, "b": b, "c": c, "d": d, "n": n},
    }
    result.update(_ror(a, b, c, d))
    return result
