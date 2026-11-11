"""File tree rendering, folder toggles, preview and editing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snakelit.types import FileStore  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

STORE = """
import streamlit as st

from snakelit.types import FileStore, Stat
from snakelit.preview import preview_for


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

from snakelit.file_explorer import FileExplorer

if "state" not in st.session_state:
    st.session_state["state"] = FileExplorer(
        key="files",
        store=Store(
            {
                "config/config.yaml": b"x: 1\\n",
                "config/README.md": b"# readme\\n",
                "LICENSE": b"MIT\\n",
            }
        ),
    )
st.session_state["state"].render()
"""


def _button(at, key):
    return next(item for item in at.button if item.key == key)


def _labels(at):
    return [item.label for item in at.button]


def _app(script=SCRIPT):
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    _button(at, "files-header-files").click()
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
    _button(at, "files-dir-config").click()
    at.run()

    assert not at.exception
    labels = _labels(at)
    assert "▾ config/" in labels
    assert "config.yaml" in labels
    assert "README.md" in labels


def test_file_preview_shows_content():
    at = _app()
    _button(at, "files-dir-config").click()
    at.run()
    _button(at, "files-file-config/config.yaml").click()
    at.run()

    assert not at.exception
    assert "x: 1" in at.code[0].value


BINARY_SCRIPT = STORE + """
from snakelit.file_explorer import FileExplorer

if "state" not in st.session_state:
    st.session_state["state"] = FileExplorer(
        key="files", store=Store({"data.gz": b"\\x1f\\x8b\\x08"})
    )
st.session_state["state"].render()
"""


def test_binary_preview_does_not_decode():
    at = _app(BINARY_SCRIPT)
    _button(at, "files-file-data.gz").click()
    at.run()

    assert not at.exception
    assert any("Binary file" in item.value for item in at.caption)


TABLE_SCRIPT = STORE + """
from snakelit.file_explorer import FileExplorer

if "state" not in st.session_state:
    st.session_state["state"] = FileExplorer(
        key="files", store=Store({"data.csv": b"a,b\\n1,2\\n"})
    )
st.session_state["state"].render()
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

    assert Store().tree() == {"a": {"b.txt": "a/b.txt"}, "c.txt": "c.txt"}


EDIT_SCRIPT = """
import streamlit as st
from snakelit.edit import text_edit

value = text_edit("old", key="v")
st.session_state["value"] = value
"""


def test_text_edit_returns_the_value():
    at = AppTest.from_string(EDIT_SCRIPT, default_timeout=60)
    at.run()

    area = next(item for item in at.text_area if item.key == "v-text")
    assert area.value == "old"

    area.set_value("new")
    at.run()

    assert at.session_state["value"] == "new"


UPLOAD_SCRIPT = STORE + """
from snakelit.file_explorer import FileExplorer

if "state" not in st.session_state:
    st.session_state["state"] = FileExplorer(
        key="files",
        store=Store({"config/config.yaml": b"x: 1\\n"}),
    )
st.session_state["state"].render()
"""


def test_upload_places_files_according_to_the_target():
    at = _app(UPLOAD_SCRIPT)

    def upload(target: str, *files: tuple[str, bytes]):
        at.text_input(key="files-upload-path").set_value(target)
        uploader = at.file_uploader(key="files-upload-files")
        uploader.clear()
        for name, data in files:
            uploader.upload(name, data)
        at.run()
        _button(at, "files-upload-button").click()
        at.run()

    upload("/new/named.txt", ("content.txt", b"named"))
    upload("more/", ("a.txt", b"A"))
    upload("many", ("b.txt", b"B"), ("c.txt", b"C"))
    upload("config", ("x.txt", b"X"))

    assert not at.exception, [str(error.value) for error in at.exception]
    files = at.session_state["state"].store.files
    assert files["new/named.txt"] == b"named"
    assert files["more/a.txt"] == b"A"
    assert files["many/b.txt"] == b"B"
    assert files["many/c.txt"] == b"C"
    assert files["config/x.txt"] == b"X"


def test_upload_reports_an_invalid_target_path():
    at = _app(UPLOAD_SCRIPT)
    at.text_input(key="files-upload-path").set_value("../x/")
    at.file_uploader(key="files-upload-files").upload("a.txt", b"A")
    at.run()

    assert [item.value for item in at.error] == ["Invalid target path: '../x/'"]
    assert not [item for item in at.button if item.key == "files-upload-button"]


def test_upload_warns_before_overwriting_an_existing_file():
    at = _app(UPLOAD_SCRIPT)
    at.text_input(key="files-upload-path").set_value("config/")
    at.file_uploader(key="files-upload-files").upload("config.yaml", b"new")
    at.run()

    assert [item.value for item in at.warning] == [
        "These files will be overwritten: config/config.yaml"
    ]


def test_upload_warns_before_overwriting_a_named_file():
    at = _app(UPLOAD_SCRIPT)
    at.text_input(key="files-upload-path").set_value("config/config.yaml")
    at.file_uploader(key="files-upload-files").upload("local.yaml", b"new")
    at.run()

    assert [item.value for item in at.warning] == [
        "This file will be overwritten: config/config.yaml"
    ]

    _button(at, "files-upload-button").click()
    at.run()

    assert not at.exception, [str(error.value) for error in at.exception]
    assert at.session_state["state"].store.files["config/config.yaml"] == b"new"


def test_upload_refuses_several_files_at_a_file_path():
    at = _app(UPLOAD_SCRIPT)
    at.text_input(key="files-upload-path").set_value("config/config.yaml")
    uploader = at.file_uploader(key="files-upload-files")
    uploader.upload("a.txt", b"A")
    uploader.upload("b.txt", b"B")
    at.run()

    assert [item.value for item in at.error] == [
        "'config/config.yaml' is a file; choose a folder path."
    ]


def _open_config_in_edit(at):
    _button(at, "files-dir-config").click()
    at.run()
    _button(at, "files-file-config/config.yaml").click()
    at.run()
    _button(at, "files-edit-toggle").click()
    at.run()
    return at.session_state["state"].store


def test_delete_opens_a_confirmation_dialog():
    at = _app()
    store = _open_config_in_edit(at)

    _button(at, "files-delete").click()
    at.run()

    assert not at.exception
    assert "config/config.yaml" in store.files
    assert _button(at, "files-cancel-delete").label == "Cancel"
    assert len(at.get("dialog")) == 1

    # cannot close the dialog in the test, use the api directly
    explorer = at.session_state["state"]
    explorer.delete("config/config.yaml")
    at.run()

    assert not at.exception
    assert "config/config.yaml" not in store.files
    assert explorer.preview is None
