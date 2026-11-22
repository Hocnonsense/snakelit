"""JSON serialization for the editor's ``format="json"`` mode."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snakelit.utils import json, yaml  # noqa: E402


def test_dump():
    assert json.dump({"a": 1}) == '{\n  "a": 1\n}\n'


def test_json_output_round_trips_through_yaml_loader():
    assert yaml.load(json.dump({"sample": "001"})) == {"sample": "001"}
