"""Row-schema coercion and validation for Polars tables."""

import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from snakelit.editor.table_schema import (  # noqa: E402
    coerce_frame,
    field_dtypes,
    schema_columns,
    table_errors,
)

SCHEMA = {
    "type": "object",
    "required": ["sample"],
    "properties": {
        "sample": {"type": "string"},
        "count": {"type": "integer"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


_NO_ARRAY_SCHEMA = {
    "type": "object",
    "properties": {"sample": {"type": "string"}},
}


def test_schema_columns_lists_properties():
    assert schema_columns(SCHEMA) == ["sample", "count", "tags"]
    assert schema_columns(None) == []


def test_field_dtypes_maps_declared_types():
    frame = pl.DataFrame(
        {"sample": ["a"], "count": ["1"], "tags": ["[]"], "other": ["x"]}
    )

    assert dict(field_dtypes(frame.columns, SCHEMA)) == {
        "sample": pl.Utf8,
        "count": pl.Int64,
        "tags": pl.List(pl.String),
        "other": None,
    }


def test_coerce_frame_casts_columns():
    frame = pl.DataFrame({"sample": ["a"], "count": ["1"]})

    coerced, changed = coerce_frame(frame, SCHEMA)

    assert changed
    assert coerced.schema["count"] == pl.Int64


def test_coerce_frame_gives_empty_columns_the_declared_dtype():
    frame = pl.DataFrame({"sample": [None], "count": [None], "tags": [None]})

    coerced, changed = coerce_frame(frame, SCHEMA)

    assert changed
    assert coerced.schema == {
        "sample": pl.String,
        "count": pl.Int64,
        "tags": pl.List(pl.String),
    }


def test_coerce_frame_decodes_json_arrays():
    frame = pl.DataFrame({"sample": ["a"], "tags": ['["x", "y"]']})

    coerced, changed = coerce_frame(frame, SCHEMA)

    assert changed
    assert coerced["tags"].to_list() == [["x", "y"]]


def test_coerce_frame_reports_multiple_values():
    frame = pl.DataFrame(
        {"sample": ["a"], "tags": pl.Series([["x", "y"]], dtype=pl.List(pl.String))}
    )
    errors: list[str] = []

    coerced, _ = coerce_frame(frame, _NO_ARRAY_SCHEMA, errors)

    assert coerced["tags"].to_list() == ["x"]
    assert any("multiple values" in message for message in errors)


def test_coerce_frame_raises_without_an_error_list():
    frame = pl.DataFrame(
        {"sample": ["a"], "tags": pl.Series([["x", "y"]], dtype=pl.List(pl.String))}
    )

    with pytest.raises(ValueError, match="multiple values"):
        coerce_frame(frame, _NO_ARRAY_SCHEMA)


def test_table_errors_reports_rows_and_required_fields():
    frame = pl.DataFrame({"sample": [""], "count": ["one"]})

    errors = table_errors(frame, SCHEMA)

    assert any("sample" in message for message in errors)


def test_valid_table_has_no_errors():
    frame = pl.DataFrame({"sample": ["a"], "count": [1]})

    assert table_errors(frame, SCHEMA) == []
