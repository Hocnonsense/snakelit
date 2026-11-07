"""File tree rendering, folder toggles, preview and editing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamlit.testing.v1 import AppTest  # noqa: E402

SCRIPT = """
import streamlit as st
from snakelit.file_view import File, Stat, file_view, text_preview

FILES = {
    "config/config.yaml": File(
        Stat(1200),
        preview=text_preview("x: 1\\n", language="yaml"),
    ),
    "config/README.md": File(Stat(800)),
    "LICENSE": File(Stat(1100), preview=text_preview("MIT\\n")),
}

file_view(FILES, key="files")
"""


def _button(at, key):
    return next(item for item in at.button if item.key == key)


def _labels(at):
    return [item.label for item in at.button]


def _app(script=SCRIPT):
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    return at


def test_tree_lists_folders_and_files():
    at = _app()

    assert not at.exception
    labels = _labels(at)
    assert "▸ config/" in labels
    assert "LICENSE" in labels
    assert "config.yaml" not in labels


def test_styles_target_documented_key_hook():
    at = _app()

    assert not at.exception
    css = "\n".join(item.value for item in at.html)
    assert ".st-key-files-tree" in css
    assert "max-height: 650px" in css
    assert "data-testid" not in css


def test_folder_toggles_open():
    at = _app()
    _button(at, "files-dir-config/").click()
    at.run()

    assert not at.exception
    labels = _labels(at)
    assert "▾ config/" in labels
    assert "config.yaml" in labels
    assert "README.md" in labels


def test_file_preview_shows_content():
    at = _app()
    _button(at, "files-dir-config/").click()
    at.run()
    _button(at, "files-file-config/config.yaml").click()
    at.run()

    assert not at.exception
    assert "x: 1" in at.code[0].value


BINARY_SCRIPT = """
from snakelit.file_view import File, Stat, file_view, preview_for

file_view(
    {
        "data.gz": File(
            Stat(3),
            preview=preview_for("data.gz", b"\\x1f\\x8b\\x08"),
        )
    },
    key="files",
)
"""


def test_binary_preview_does_not_decode():
    at = _app(BINARY_SCRIPT)
    _button(at, "files-file-data.gz").click()
    at.run()

    assert not at.exception
    assert any("Binary file" in item.value for item in at.caption)


TABLE_SCRIPT = """
from snakelit.file_view import File, Stat, file_view, preview_for

file_view(
    {
        "data.csv": File(
            Stat(6),
            preview=preview_for("data.csv", b"a,b\\n1,2\\n"),
        )
    },
    key="files",
)
"""


def test_table_preview_reads_csv():
    at = _app(TABLE_SCRIPT)
    _button(at, "files-file-data.csv").click()
    at.run()

    assert not at.exception
    assert len(at.dataframe) == 1
