"""File suffixes grouped by how snakelit renders them."""

from __future__ import annotations

from pathlib import Path

TABLE_SUFFIXES = ("tsv", "csv", "xlsx", "parquet")
IMAGE_SUFFIXES = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
BINARY_SUFFIXES = {
    "bin",
    "dat",
    "exe",
    "dll",
    "so",
    "o",
    "a",
    "class",
    "xlsx",
    "parquet",
}
LANGUAGE_BY_SUFFIX = {
    "yaml": "yaml",
    "yml": "yaml",
    "json": "json",
    "py": "python",
    "smk": "python",
    "md": "markdown",
    "sh": "bash",
    "toml": "toml",
    "csv": "csv",
    "tsv": "tsv",
}


def suffix(path: str) -> str:
    """The lowercase suffix of ``path``, without the leading dot."""
    return Path(path).suffix.lower().lstrip(".")
