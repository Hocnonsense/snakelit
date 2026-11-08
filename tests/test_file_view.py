"""File tree rendering, folder toggles, preview and editing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snakelit.types import FileStore  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

STORE = """
import streamlit as st

from snakelit.types import FileStore, Stat
from snakelit.file_view import preview_for


class Store(FileStore):
    def __init__(self, files):
        self.files = files

    def paths(self):
        return list(self.files)

    def stat(self, path):
        content = self.files.get(str(path))
        return None if content is None else Stat(len(content))

    def show(self, path, mode="Preview"):
        content = self.files.get(str(path))
        if content is None:
            return None
        if mode == "Edit":
            return lambda: st.caption(f"Editing `{path}`")
        return lambda: preview_for(str(path), content)

    def read(self, path):
        return self.files.get(str(path))

    def write(self, path, data):
        self.files[str(path)] = data

    def rm(self, path):
        self.files.pop(str(path), None)
"""

SCRIPT = STORE + """
import streamlit as st

from snakelit.file_view import file_explorer

if "store" not in st.session_state:
    st.session_state["store"] = Store(
        {
            "config/config.yaml": b"x: 1\\n",
            "config/README.md": b"# readme\\n",
            "LICENSE": b"MIT\\n",
        }
    )
file_explorer(st.session_state["store"], key="files")
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
    css = "\n".join(item.value for item in getattr(at, "html"))
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


BINARY_SCRIPT = STORE + """
from snakelit.file_view import file_explorer

file_explorer(Store({"data.gz": b"\\x1f\\x8b\\x08"}), key="files")
"""


def test_binary_preview_does_not_decode():
    at = _app(BINARY_SCRIPT)
    _button(at, "files-file-data.gz").click()
    at.run()

    assert not at.exception
    assert any("Binary file" in item.value for item in at.caption)


TABLE_SCRIPT = STORE + """
from snakelit.file_view import file_explorer

file_explorer(Store({"data.csv": b"a,b\\n1,2\\n"}), key="files")
"""


def test_table_preview_reads_csv():
    at = _app(TABLE_SCRIPT)
    _button(at, "files-file-data.csv").click()
    at.run()

    assert not at.exception
    assert len(at.dataframe) == 1


def test_tree_is_derived_from_paths():
    class Store(FileStore):
        def paths(self):
            return ["a/b.txt", "c.txt"]

        def stat(self, path):
            raise NotImplementedError

        def show(self, path, mode="Preview"):
            raise NotImplementedError

        def read(self, path):
            raise NotImplementedError

        def write(self, path, data):
            raise NotImplementedError

        def rm(self, path):
            raise NotImplementedError

    assert Store().tree() == {"a/": {"b.txt": "a/b.txt"}, "c.txt": "c.txt"}


EDIT_SCRIPT = """
import streamlit as st
from snakelit.file_view import text_edit

value = text_edit("old", key="v")
st.session_state["value"] = value
"""


def test_text_edit_returns_the_value():
    at = _app(EDIT_SCRIPT)

    area = next(item for item in at.text_area if item.key == "v-text")
    assert area.value == "old"

    area.set_value("new")
    at.run()

    assert at.session_state["value"] == "new"
