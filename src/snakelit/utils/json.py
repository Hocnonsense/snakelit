"""JSON helpers, mirroring :mod:`snakelit.utils.yaml`."""

from __future__ import annotations

import json


def dump(data):
    """Serialize ``data`` as indented JSON with a trailing newline."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
