"""Serialize workflow configuration as JSON."""

import json

# use yaml.load to load json.


def dump(data):
    """Serialize ``data`` as indented JSON with a trailing newline."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
