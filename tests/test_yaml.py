"""YAML round trips for the scientific-float convention."""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snakelit.utils.yaml import dump, load  # noqa: E402


def test_scientific_float_loads_as_string():
    assert load("threshold: 1e-5\n") == {"threshold": "1e-5"}


def test_plain_float_stays_float():
    assert load("alpha: 0.5\n") == {"alpha": 0.5}


def test_errors_are_collected_instead_of_raised():
    errors: list[str] = []

    assert load("a: [\n", errors) is None
    assert errors and "expected" in errors[0].lower()


def test_load_raises_without_an_error_list():
    with pytest.raises(yaml.YAMLError):
        load("a: [\n")


def test_marked_string_dumps_as_float():
    dumped = dump({"threshold": "1e-5scn"})

    assert dumped == "threshold: !!float '1e-5'\n"
    # other tools must see a float, so the marker is not part of the output
    assert yaml.safe_load(dumped) == {"threshold": 1e-05}


def test_dump_keeps_key_order():
    assert dump({"b": 1, "a": 2}) == "b: 1\na: 2\n"
