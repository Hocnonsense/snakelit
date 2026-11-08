"""JSON serialization for the editor's ``format="json"`` mode."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snakelit.utils.json import dump  # noqa: E402


def test_dump():
    assert dump({"a": 1}) == '{\n  "a": 1\n}\n'
