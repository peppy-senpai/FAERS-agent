"""Parse uploaded FAERS files and load them into a project's working database.

The upload path is: raw bytes → Polars DataFrame → a table in
``working_db_<project_id>``. Polars does the parsing (fast, handles the big
quarterly files) and ADBC does the bulk load over Arrow, so nothing round-trips
through pandas.

Design choices:
  • Every column is loaded as **text**. FAERS ids (primaryid, caseid) are long
    integers that lose precision or gain a stray ``.0`` under numeric inference,
    and the downstream SQL tools filter by equality anyway. Text is faithful.
  • Column names are normalised to ``[a-z0-9_]`` so the reflected tables are
    queryable without quoting.
  • FAERS legacy ASCII files are ``$``-delimited; the separator is sniffed.
"""

from __future__ import annotations

import io
import re

import polars as pl

from .working_db import working_db_url

# Extensions we know how to parse. Anything else is rejected with a clear error
# rather than a 500.
_CSV_LIKE = {"csv", "txt", "tsv", "dat"}
SUPPORTED = _CSV_LIKE | {"xlsx", "xls", "json", "ndjson", "parquet"}

# Separators considered when sniffing a delimited text file.
_SEPARATORS = ("$", "\t", "|", ",", ";")


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _decode_to_utf8_bytes(data: bytes) -> bytes:
    """Return ``data`` re-encoded as UTF-8.

    Polars' CSV reader is UTF-8 only, but older FAERS dumps are latin-1. Try
    UTF-8 first, fall back to latin-1, and as a last resort replace bad bytes
    so a single stray character never fails the whole upload.
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding).encode("utf-8")
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace").encode("utf-8")


def _sniff_separator(first_line: str) -> str:
    """Guess the delimiter of a text file from its header line."""
    counts = {sep: first_line.count(sep) for sep in _SEPARATORS}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _normalize_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Rename columns to unique, unquoted-safe ``[a-z0-9_]`` identifiers."""
    seen: dict[str, int] = {}
    renames: dict[str, str] = {}
    for original in df.columns:
        name = re.sub(r"[^a-z0-9_]", "_", original.strip().lower()).strip("_")
        name = (name or "col")[:63]
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"[:63]
        else:
            seen[name] = 0
        renames[original] = name
    return df.rename(renames)


def _as_text(df: pl.DataFrame) -> pl.DataFrame:
    """Cast every column to Utf8 so ids and codes survive intact."""
    return df.select(pl.all().cast(pl.Utf8))


def read_any(filename: str, data: bytes) -> pl.DataFrame:
    """Parse uploaded bytes into an all-text Polars DataFrame.

    Routes by file extension. Raises :class:`ValueError` for unsupported types.
    """
    ext = _extension(filename)
    if ext not in SUPPORTED:
        raise ValueError(
            f"Unsupported file type {ext!r}. Supported: "
            + ", ".join(sorted(SUPPORTED))
        )

    if ext in _CSV_LIKE:
        text_bytes = _decode_to_utf8_bytes(data)
        header = text_bytes.split(b"\n", 1)[0].decode("utf-8", errors="replace")
        separator = "\t" if ext == "tsv" else _sniff_separator(header)
        df = pl.read_csv(
            io.BytesIO(text_bytes),
            separator=separator,
            infer_schema_length=0,  # all columns as text
            truncate_ragged_lines=True,  # tolerate FAERS trailing '$'
        )
    elif ext in {"xlsx", "xls"}:
        df = pl.read_excel(io.BytesIO(data))
    elif ext == "parquet":
        df = pl.read_parquet(io.BytesIO(data))
    elif ext == "ndjson":
        df = pl.read_ndjson(io.BytesIO(data))
    else:  # json — try records array, fall back to newline-delimited
        try:
            df = pl.read_json(io.BytesIO(data))
        except Exception:
            df = pl.read_ndjson(io.BytesIO(data))

    if df.width == 0:
        raise ValueError("File produced no columns — is it empty or malformed?")

    return _as_text(_normalize_columns(df))


def derive_table_name(filename: str) -> str:
    """Suggest a table name from a filename, e.g. ``DRUG24Q1.txt`` → ``drug``.

    Strips the extension and a trailing FAERS quarter/date token, then sanitises
    to a safe identifier.
    """
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    stem = stem.lower()
    # Drop a trailing quarter token like 24q1 / 2024q1, or trailing digits.
    stem = re.sub(r"[_\- ]*\d{2,4}q[1-4]$", "", stem)
    stem = re.sub(r"[_\- ]*\d{4,8}$", "", stem)
    name = re.sub(r"[^a-z0-9_]", "_", stem).strip("_")
    return (name or "table")[:63]


def load_dataframe(
    df: pl.DataFrame,
    project_id: str,
    table_name: str,
    mode: str = "replace",
) -> int:
    """Bulk-load ``df`` into ``table_name`` of the project's working database.

    ``mode`` is one of ``replace`` (drop + recreate) or ``append``. Uses the
    ADBC engine so the load goes over Arrow rather than through pandas. Returns
    the number of rows written.
    """
    if mode not in {"replace", "append"}:
        raise ValueError(f"mode must be 'replace' or 'append', got {mode!r}")

    # ADBC's libpq driver wants a plain postgres URI, not the SQLAlchemy
    # "postgresql+psycopg" dialect form.
    uri = working_db_url(project_id).set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    df.write_database(
        table_name,
        uri,
        if_table_exists=mode,
        engine="adbc",
    )
    return df.height
