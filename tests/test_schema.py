"""Schema introspection and validation helpers."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snakelit.utils.schema import (  # noqa: E402
    get_property_type,
    is_schema,
    validate,
)

SCHEMA = {
    "type": "object",
    "required": ["samples"],
    "properties": {
        "samples": {"type": "string"},
        "threads": {"type": "integer", "minimum": 1},
    },
}


def test_validation_reports_path_and_message():
    assert list(validate({"samples": "s.tsv", "threads": 0}, SCHEMA)) == [
        "threads: 0 is less than the minimum of 1"
    ]


def test_valid_config_has_no_errors():
    assert list(validate({"samples": "s.tsv", "threads": 2}, SCHEMA)) == []


def test_missing_schema_is_not_validated():
    assert list(validate({"anything": 1}, None)) == []


def test_missing_required_is_reported_once():
    # jsonschema's ``required`` keyword handles absence ...
    assert list(validate({}, SCHEMA)) == ["<root>: 'samples' is a required property"]


def test_empty_required_value_is_reported():
    # ... but it accepts an empty string, so the explicit check adds this one.
    assert list(validate({"samples": ""}, SCHEMA)) == [
        "samples: required value is empty"
    ]


def test_present_required_value_is_valid():
    assert list(validate({"samples": "s.tsv"}, SCHEMA)) == []


def test_property_type_detection():
    assert get_property_type({"properties": {}}) == "properties"
    assert get_property_type({"patternProperties": {}}) == "patternProperties"
    with pytest.raises(ValueError):
        get_property_type({})
    assert is_schema({"properties": {}})
    assert not is_schema({"type": "string"})
    assert not is_schema(None)
