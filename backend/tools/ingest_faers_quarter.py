"""FAERS quarter ingestion tool.

Wraps the demo/drug/reac ingestion + cleaning + join pipeline (originally a
notebook) into a single agent-callable tool. It reads the ``$``-delimited FAERS
ASCII files for one quarter, cleans and de-duplicates each table, keeps
primary-suspect (``PS``) drugs, and joins them into one analysis-ready dataset
(demographics + drug + reaction).

Returns a compact summary (never the full frame, which can be millions of rows);
pass ``output_path`` to also persist the combined table as Parquet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from langchain_core.tools import tool


def _build_combined(data_dir: Path, quarter: str) -> pl.DataFrame:
    """Read, clean, and join the DEMO/DRUG/REAC files for ``quarter``."""
    q = quarter.upper()

    demo = pl.read_csv(
        data_dir / f"DEMO{q}.txt",
        separator="$",
        schema_overrides={"primaryid": pl.String, "caseid": pl.String},
        encoding="utf8-lossy",
        infer_schema_length=10_000,
    )
    drug = pl.read_csv(
        data_dir / f"DRUG{q}.txt",
        separator="$",
        schema_overrides={
            "primaryid": pl.String,
            "caseid": pl.String,
            "dose_amt": pl.Float64,
        },
        encoding="utf8-lossy",
        infer_schema_length=10_000,
    )
    reac = pl.read_csv(
        data_dir / f"REAC{q}.txt",
        separator="$",
        schema_overrides={"primaryid": pl.String, "caseid": pl.String},
        encoding="utf8-lossy",
        infer_schema_length=10_000,
    )

    # Clean reactions: drop the mostly-empty drug_rec_act, de-dupe, normalise ids.
    reac = (
        reac.drop("drug_rec_act")
        .unique()
        .with_columns(
            pl.col("primaryid").cast(pl.String),
            pl.col("caseid").cast(pl.String),
        )
    )

    # Clean drugs: keep the analysis columns and de-dupe.
    drug = (
        drug.select(["primaryid", "drugname", "prod_ai", "role_cod"])
        .unique()
        .with_columns(pl.col("primaryid").cast(pl.String))
    )

    # Clean demographics: keep analysis columns, require an age, type the fields.
    demo = (
        demo.select(["primaryid", "age", "sex", "event_dt", "occr_country"])
        .drop_nulls(subset=["age"])
        .unique()
        .with_columns(
            pl.col("primaryid").cast(pl.String),
            pl.col("sex").cast(pl.Categorical),
            pl.col("event_dt").cast(pl.String).str.to_date("%Y%m%d", strict=False),
            pl.col("occr_country").cast(pl.Categorical),
        )
    )

    # Keep only primary-suspect drugs, then join demo → drug → reactions.
    drug = drug.filter(pl.col("role_cod") == "PS").drop("role_cod")
    combined = demo.join(drug, on="primaryid", how="left").join(
        reac, on="primaryid", how="left"
    )

    return combined.unique(
        subset=["age", "sex", "event_dt", "occr_country", "drugname", "prod_ai", "pt"],
        keep="first",
    )


@tool
def ingest_faers_quarter(
    data_dir: str,
    quarter: str,
    output_path: str = "",
) -> dict[str, Any]:
    """Ingest and clean one FAERS quarter into a single combined table.

    Reads the DEMO/DRUG/REAC ASCII files for the quarter, cleans and de-duplicates
    them, keeps primary-suspect (PS) drugs, and joins them into one
    analysis-ready dataset (demographics + drug + reaction).

    Args:
        data_dir: Folder containing the FAERS ASCII files (the "ASCII" directory),
            holding DEMO<quarter>.txt, DRUG<quarter>.txt, REAC<quarter>.txt.
        quarter: FAERS quarter code such as "26Q1" (matches the filename suffix).
        output_path: Optional path to write the combined table as Parquet. When
            set, the file is written and its path is returned.

    Returns:
        A summary with the quarter, combined row count, column names, and the
        output path when one was written. On failure, ``ok`` is False with an
        ``error`` message instead of raising.
    """
    try:
        folder = Path(data_dir)
        combined = _build_combined(folder, quarter)
    except Exception as exc:  # noqa: BLE001 - return the error to the agent
        return {"ok": False, "quarter": quarter.upper(), "error": str(exc)}

    result: dict[str, Any] = {
        "ok": True,
        "quarter": quarter.upper(),
        "rows": combined.height,
        "columns": combined.columns,
    }
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        combined.write_parquet(out)
        result["output_path"] = str(out)
    return result
