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
    """Drop empty/null cells from a row, as Snakemake does before validation.

    Snakemake's ``validate`` excludes NULL values from each record, so an empty
    cell means "absent" (governed by the schema's ``required`` list) rather than
    a value that must match the declared type.
    """
    return {
        key: value for key, value in row.items() if value is not None and value != ""
    }


def table_errors(table: pl.DataFrame | None, schema: Mapping | None):
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
    """Yield ``(field, dtype)`` for every field in ``fields``.

    A declared ``array`` field maps to ``List(String)`` and a declared primitive
    to its dtype; a field the schema does not constrain (absent from
    ``properties`` or without a recognised ``type``) yields ``None`` -- the caller
    leaves that column untouched.  JSON Schema allows unlisted properties by
    default, so an unconstrained field is not an error.
    """
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
    """Make ``frame`` match ``schema``.

    A ``List(String)`` column the schema does not declare ``array`` holds at most
    one value per row: several are an issue, one becomes the value, none becomes
    null.  Declared ``array`` columns are kept as lists (a stored JSON string is
    decoded).  Declared primitive columns are cast to their types.  A value that
    cannot be converted is left unchanged so validation can report it.  Returns
    ``(frame, changed)``.
    """
    changed = False
    for column, dtype in field_dtypes(frame.columns, schema):
        current = frame.schema[column]
        if current == _ARRAY_DTYPE and dtype != _ARRAY_DTYPE:
            # A pivot list the schema does not declare ``array``: at most one
            # value per row (several are an issue).
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
        if current == pl.Null:
            # An empty/all-null column has no values to infer from; give it
            # the declared dtype instead of leaving it as Null.
            frame = frame.with_columns(pl.col(column).cast(dtype))
            changed = True
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


def nullify(example: Mapping):
    """Canonicalize a columnar example: empty strings become ``None`` (absent).

    A table cell cannot distinguish ``""`` from missing, so the model keeps a
    single empty representation (``None``); this keeps the sidecar free of a
    mix of ``null`` and ``''``.
    """
    return {
        column: [None if value == "" else value for value in values]
        for column, values in example.items()
    }


def _json_type(dtype: pl.DataType):
    if dtype.is_integer():
        return "integer"
    if dtype.is_float():
        return "number"
    if dtype == pl.Boolean:
        return "boolean"
    return "string"


def infer_table_schema(table: pl.DataFrame):
    """Infer a row schema (an object of typed properties) from a table."""
    return {
        "type": "object",
        "properties": {
            column: _column_schema(table.schema[column]) for column in table.columns
        },
    }


def _column_schema(dtype: pl.DataType):
    if dtype.is_nested():
        return {"type": "array", "items": {"type": "string"}}
    return {"type": _json_type(dtype)}
