"""Byte-level table loading and dumping (polars is imported lazily)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import IO, TYPE_CHECKING, Mapping

from ..filetypes import TABLE_SUFFIXES

if TYPE_CHECKING:
    import polars as pl


def _extension(source, suffix: str | None) -> str:
    """The suffix without the dot, from an explicit one, a path or a named stream."""
    if suffix:
        return suffix.lower().lstrip(".")
    name = source if isinstance(source, (str, Path)) else getattr(source, "name", "")
    if not isinstance(name, (str, Path)):
        return ""
    return Path(name).suffix.lower().lstrip(".")


def load(
    source: str | Path | IO[bytes] | bytes,
    suffix: str | None = None,
    schema: Mapping[str, pl.DataType | type[pl.DataType]] | None = None,
    infer: bool = False,
    limit: int | None = None,
    *,
    errors: list[str] | None = None,
) -> pl.DataFrame | None:
    """Read a table by extension, or ``None`` when it cannot be read.

    ``source`` is a path or a binary buffer/-stream; pass ``suffix`` when it is
    not a path.  ``schema`` gives strict per-column dtype overrides; ``infer``
    selects how the remaining columns are read.  ``limit`` caps the rows read
    where the parser supports it (and truncates the rest afterwards).
    Combining them yields four modes:

    ============ ===================================================
    (None, False) every column as string (``infer_schema_length=0``),
                  the ``dtype=str`` convention of Snakemake sample
                  sheets: identifiers such as ``unit`` stay strings
    (None, True)  Polars' default type inference
    (schema, *)   ``schema`` columns keep their dtype; the rest follow
                  ``infer`` (strings or inferred)
    ============ ===================================================

    Failures are appended to ``errors`` and yield ``None``; without ``errors``
    the original exception is raised, so probing code opts out explicitly.
    """
    import polars as pl

    kwargs: dict = dict(
        schema_overrides=dict(schema) if schema else None,
        infer_schema_length=None if infer else 0,
    )
    ext = _extension(source, suffix)
    if ext not in TABLE_SUFFIXES:
        message = f"Unsupported table format: {ext or '(none)'}"
        if errors is None:
            raise ValueError(message)
        errors.append(message)
        return None
    try:
        if ext == "parquet":
            return pl.read_parquet(source, n_rows=limit)
        if ext == "tsv":
            return pl.read_csv(source, separator="\t", n_rows=limit, **kwargs)
        if ext == "csv":
            return pl.read_csv(source, n_rows=limit, **kwargs)
        if ext == "xlsx":
            table = pl.read_excel(source, **kwargs)
            return table.head(limit) if limit is not None else table
    except Exception as error:  # noqa: BLE001 - reported to the caller
        if errors is None:
            raise
        errors.append(f"Could not read the {ext or 'table'}: {error}")
        return None


def dump(data: pl.DataFrame, suffix: str = "csv") -> bytes:
    """Serialize ``data`` to bytes in the format named by ``suffix``."""
    ext = _extension("", suffix)
    buffer = BytesIO()
    if ext == "parquet":
        data.write_parquet(buffer)
    elif ext == "tsv":
        data.write_csv(buffer, separator="\t")
    elif ext == "csv":
        data.write_csv(buffer)
    elif ext == "xlsx":
        data.write_excel(buffer)
    else:
        raise ValueError(
            f"Unsupported table format: {suffix}. "
            "Supported formats are: tsv, csv, xlsx, parquet",
        )
    return buffer.getvalue()
