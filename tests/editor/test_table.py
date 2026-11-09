"""Widget-level tests for the editable table."""

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

SCRIPT = """
import polars as pl
import streamlit as st
from snakelit.editor.table import form_table

if "frame" not in st.session_state:
    st.session_state["frame"] = pl.DataFrame({"sample": ["a"], "count": [1]})
errors = []
edited = form_table(st.session_state["frame"], errors, key="t")
st.session_state["edited"] = edited
st.session_state["errors"] = errors
"""


def _app(script=SCRIPT):
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    return at


def _button(at, key):
    return next(item for item in at.button if item.key == key)


def test_renders_the_table_without_errors():
    at = _app()

    assert not at.exception, [str(error.value) for error in at.exception]
    assert at.session_state["errors"] == []
    assert at.session_state["edited"].columns == ["sample", "count"]


def test_column_operations_return_the_edited_table():
    at = _app()

    at.text_input(key="t-new-column").set_value("extra")
    _button(at, "t-add-column").click()
    at.run()

    at.selectbox(key="t-rename-column").set_value("sample")
    at.text_input(key="t-rename-column-text").set_value("id")
    _button(at, "t-rename-column-button").click()
    at.run()

    at.selectbox(key="t-remove-column").set_value("count")
    _button(at, "t-remove-column-button").click()
    at.run()

    at.selectbox(key="t-move-column").set_value("id")
    at.selectbox(key="t-move-target").set_value("(end)")
    _button(at, "t-move-button").click()
    at.run()

    edited = at.session_state["edited"]
    assert edited.columns == ["extra", "id"]
    assert edited.to_dict(as_series=False) == {"extra": [""], "id": ["a"]}


SCHEMA_SCRIPT = """
import polars as pl
import streamlit as st
from snakelit.editor.table import form_table

SCHEMA = {
    "type": "object",
    "required": ["sample"],
    "properties": {"sample": {"type": "string"}, "count": {"type": "integer"}},
}
if "frame" not in st.session_state:
    st.session_state["frame"] = pl.DataFrame({"sample": [""], "count": [1]})
errors = []
edited = form_table(st.session_state["frame"], errors, SCHEMA, key="t")
st.session_state["errors"] = errors
"""


def test_schema_errors_are_reported():
    at = _app(SCHEMA_SCRIPT)

    assert any("required" in message for message in at.session_state["errors"])


def test_load_and_dump_accept_a_suffix_without_dot():
    from snakelit.utils.table import dump, load

    frame = load(b"a,b\n1,2\n", suffix="csv")

    assert frame is not None
    assert frame.shape == (1, 2)
    assert dump(frame, "csv") == b"a,b\n1,2\n"


def test_load_reports_an_unsupported_suffix():
    from snakelit.utils.table import load

    errors: list[str] = []

    assert load(b"a,b\n1,2\n", errors=errors) is None
    assert errors == ["Unsupported table format: (none)"]


def test_schema_table_repairs_broken_tables_in_the_text_editor():
    at = _app("""
import streamlit as st
from snakelit.editor.table import schema_table

errors = []
updated = schema_table(b"a,b\\n1,2,3\\n", errors, None, key="t", format="csv")
st.session_state["errors"] = errors
st.session_state["updated"] = updated
""")

    assert not at.exception
    editor = next(item for item in at.text_area if item.key == "t-editor")
    assert editor.value == "a,b\n1,2,3\n"
    assert any("Could not read" in message for message in at.session_state["errors"])
    assert at.session_state["updated"] is None

    editor.set_value("a,b\n1,2\n")
    at.run()

    assert at.session_state["errors"] == []
    assert at.session_state["updated"] == b"a,b\n1,2\n"


def test_schema_table_refuses_broken_binary_tables():
    at = _app("""
import streamlit as st
from snakelit.editor.table import schema_table

errors = []
updated = schema_table(b"\\x00\\x01", errors, None, key="t", format="parquet")
st.session_state["errors"] = errors
st.session_state["updated"] = updated
""")

    assert not at.exception
    assert at.session_state["updated"] is None
