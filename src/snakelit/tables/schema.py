"""Row-schema coercion and validation for Polars tables.

A table's row schema is a JSON schema of one record: coercion casts columns to
their declared dtypes and decodes array cells, validation checks each row.
Nothing here touches the filesystem.
"""

from __future__ import annotations

from typing import Iterable, Mapping

import polars as pl

from ..utils.schema import validate

_ARRAY_DTYPE = pl.List(pl.String)

_PRIMITIVE_DTYPES: dict[str, type[pl.DataType]] = {
    "string": pl.Utf8,
    "integer": pl.Int64,
    "number": pl.Float64,
    "boolean": pl.Boolean,
}


def validate_values(row: Mapping):
    """Drop empty/null cells, as Snakemake does before validating a record."""
    return {
        key: value for key, value in row.items() if value is not None and value != ""
    }


def table_errors(table: pl.DataFrame, schema: Mapping | None):
    """Validate every row of ``table`` against the row ``schema``."""
    errors: list[str] = []
    if not schema or table is None:
        return errors
    for index, row in enumerate(table.iter_rows(named=True)):
        for message in validate(validate_values(row), schema):
            errors.append(f"row {index}: {message}")
    return errors


def schema_columns(schema) -> list[str]:
    """The declared column names of a table row schema."""
    properties = schema.get("properties") if isinstance(schema, dict) else None
    return list(properties) if isinstance(properties, dict) else []


def field_dtypes(fields: Iterable[str], schema: Mapping):
    """Yield ``(field, dtype)`` for the declared types in ``fields``."""
    properties = schema.get("properties") if isinstance(schema, dict) else None
    properties = properties if isinstance(properties, dict) else {}
    for name in fields:
        sub = properties.get(name)
        field_type = sub.get("type") if isinstance(sub, dict) else None
        yield name, _declared_dtype(field_type)


def _declared_dtype(field_type):
    if isinstance(field_type, (str, list)):
        if "array" in field_type:
            return _ARRAY_DTYPE
        if field_type in _PRIMITIVE_DTYPES:
            return _PRIMITIVE_DTYPES[field_type]


def coerce_frame(
    frame: pl.DataFrame,
    schema: Mapping,
    errors: list[str] | None = None,
):
    """Make ``frame`` match ``schema``; returns ``(frame, changed)``.

    Values that cannot be converted are left unchanged so validation can report
    them; multiple values in a column the schema does not declare ``array`` are
    reported (or raised when ``errors`` is ``None``).
    """
    changed = False
    for column, dtype in field_dtypes(frame.columns, schema):
        current = frame.schema[column]
        if current == _ARRAY_DTYPE and dtype != _ARRAY_DTYPE:
            lengths = frame[column].list.len().to_list()
            failing = [i for i, n in enumerate(lengths) if (n or 0) > 1]
            if failing:
                rows = ", ".join(str(i) for i in failing)
                message = f"column '{column}' has multiple values in row(s) {rows}"
                if errors is None:
                    raise ValueError(message)
                errors.append(message)
            frame = frame.with_columns(pl.col(column).list.first().alias(column))
            current = frame.schema[column]
            changed = True
        if dtype is None or current == dtype:
            continue
        if dtype == _ARRAY_DTYPE:
            try:
                frame = frame.with_columns(
                    pl.col(column).str.json_decode(_ARRAY_DTYPE).alias(column)
                )
            except Exception:  # noqa: BLE001 - unparseable values stay as-is
                continue
            changed = True
            continue
        if current == pl.Utf8 and dtype != pl.Utf8:
            frame = frame.with_columns(pl.col(column).replace("", None))
        try:
            frame = frame.with_columns(pl.col(column).cast(dtype))
        except Exception:  # noqa: BLE001 - unparseable values stay as-is
            continue
        changed = True
    return frame, changed
