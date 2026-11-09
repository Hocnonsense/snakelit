"""Byte-level table reading, writing and dumping (polars is imported lazily)."""

from __future__ import annotations

from pathlib import Path
from typing import IO, TYPE_CHECKING, Mapping
from io import BytesIO

import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

if TYPE_CHECKING:
    import polars as pl


def read(
    source: str | Path | IO[bytes] | bytes,
    suffix: str | None = None,
    schema: Mapping[str, pl.DataType | type[pl.DataType]] | None = None,
    infer: bool = False,
    limit: int | None = None,
) -> pl.DataFrame | None:
    """Read a table by extension, or ``None`` when unreadable/unsupported.

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
    """
    import polars as pl

    kwargs: dict = dict(
        schema_overrides=dict(schema) if schema else None,
        infer_schema_length=None if infer else 0,
    )
    suffix = (suffix or getattr(source, "suffix", "")).lower()
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"
    try:
        if suffix == ".parquet":
            return pl.read_parquet(source, n_rows=limit)
        if suffix == ".tsv":
            return pl.read_csv(source, separator="\t", n_rows=limit, **kwargs)
        if suffix == ".csv":
            return pl.read_csv(source, n_rows=limit, **kwargs)
        if suffix == ".xlsx":
            table = pl.read_excel(source, **kwargs)
            return table.head(limit) if limit is not None else table
    except Exception:
        pass


def enforce_typing(data: pl.DataFrame, schema: dict):
    """Enforces data types of a Polars DataFrame based on a provided schema.

    :param data: The input DataFrame whose columns need to be typed according
        to the schema.
    :param schema: A dictionary schema containing column names and their
        corresponding types.
    :returns: The DataFrame with columns cast to the specified types as per the schema.
    :raises polars.InvalidOperationError: If a type conversion fails.
    """
    import polars as pl

    for field, field_info in schema.get("properties", {}).items():
        match field_info["type"]:
            case typing if typing == "string":
                field_type = str
            case typing if typing == "number":
                field_type = float if "." in str(data.select(pl.first(field))) else int
        try:
            # Cast the column to the specified type
            data = data.with_columns(pl.col(field).cast(field_type))
            padding_value = get_type_specific_default(data[field].dtype)
            data = data.with_columns(pl.col(field).fill_null(padding_value))
        except pl.exceptions.InvalidOperationError:
            st.error(
                f"Failed to translate column '{field}' to match type '{field_type}'",
            )
            st.stop()
    return data


def get_type_specific_default(dtype: pl.DataType):
    """Return the appropriate padding value based on the column's data type.

    :param dtype: The Polars data type of the column.
    :returns: The padding value based on the type.
        - `""` for string columns.
        - `nan` for float columns.
        - `0` for integer columns.
        - None for unsupported data types.
    """
    import polars as pl

    if dtype in ("String", pl.Utf8):
        return ""
    if dtype in ("Float64", pl.Float64):
        return float("nan")
    if dtype in ("Int64", pl.Int64):
        return 0
    return None


def load(file: UploadedFile | Path, source: str = "file"):
    """Load a data table from an uploaded file or a file path based on the source.

    :param file: The uploaded file or file path to load the data from.
    :param source: The source of the file - either 'upload' or 'file'.
        Defaults to 'file'.
    :returns: The loaded data table as a Polars DataFrame.
    :raises FileNotFoundError: If the file does not exist when source is 'file'.
    :raises StreamlitError: For unsupported file formats or missing files.
    """
    import polars as pl

    def read_data(file: UploadedFile | Path, file_type: str):
        if file_type in ["text/tab-separated-values", ".tsv"]:
            return pl.read_csv(file, separator="\t")
        if file_type in ["text/csv", ".csv"]:
            return pl.read_csv(file)
        if file_type in [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsx",
        ]:
            return pl.read_excel(file)
        st.error(
            f"""Unsupported file format for sample sheet {file.name},
             Use: TSV, CSV or XLSX""",
        )
        st.stop()
        return None

    file_type = file.type if source == "upload" else file.suffix  # type: ignore[reportAttributeAccessIssue]
    if source == "upload":
        return read_data(file, file_type)
    try:
        return read_data(file, file_type)
    except FileNotFoundError:
        st.error(f"File {file.name} does not exist")
        return None


def save(data: pl.DataFrame, path: str | Path | IO[bytes], suffix: str | None = None):
    """Save a data table to a file based on the file extension.

    :param data: The Polars DataFrame to save.
    :param path: The file path where the data should be saved.
    :raises ValueError: If the file extension is unsupported.
    :raises IOError: If there is an issue with file writing
        (e.g., permissions or disk space).
    :raises polars.exceptions.PolarsError: For Polars-specific errors.
    """
    import polars as pl

    if not suffix:
        if isinstance(path, (str, Path)):
            suffix = Path(path).suffix
        else:
            suffix = Path(path.name).suffix
    suffix = (suffix or "").lower()
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"
    try:
        if suffix == ".parquet":
            data.write_parquet(path)
        elif suffix == ".tsv":
            data.write_csv(path, separator="\t")
        elif suffix == ".csv":
            data.write_csv(path)
        elif suffix == ".xlsx":
            data.write_excel(path)
        else:
            raise ValueError(
                f"""Unsupported file format: {suffix}.
                Supported formats are: TSV, CSV, XLSX""",
            )
    except OSError as os_error:
        raise OSError(
            f"File writing failed due to an I/O error: {os_error}",
        ) from os_error
    except pl.exceptions.PolarsError as polars_error:
        raise pl.exceptions.PolarsError(
            f"Polars encountered an error: {polars_error}",
        ) from polars_error


def dump(data: pl.DataFrame, suffix="csv"):
    """Serialize a Polars DataFrame to bytes based on the file extension.

    :param data: The Polars DataFrame to serialize.
    :param suffix: The file extension indicating the desired format.
        Supported formats are: TSV, CSV, XLSX, Parquet.
    :returns: The serialized data as bytes.
    :raises ValueError: If the file extension is unsupported.
    :raises polars.exceptions.PolarsError: For Polars-specific errors during serialization.
    """
    buffer = BytesIO()
    save(data, buffer, suffix=suffix)
    return buffer.getvalue()
