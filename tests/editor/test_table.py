"""Widget-level tests for the editable table."""

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import polars as pl  # noqa: E402

from snakelit.editor.table import _drop_empty_rows  # noqa: E402

SCRIPT = """
import polars as pl
import streamlit as st
from snakelit.editor.table import form_table

if "frame" not in st.session_state:
    st.session_state["frame"] = pl.DataFrame({"sample": ["a"], "count": [1]})
errors = []
edited = form_table(st.session_state["frame"], errors, key="t")
st.session_state["edited"] = edited
st.session_state["frame"] = edited
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


ROW_SCHEMA_SCRIPT = """
import streamlit as st
from snakelit.editor.table import schema_table

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"sample": {"type": "string"}, "count": {"type": "integer"}},
}
errors = []
updated = schema_table(b"sample\\tcount\\na\\t1\\n", errors, SCHEMA, key="t", format="tsv")
st.session_state["errors"] = errors
st.session_state["updated"] = updated
"""


def test_schema_table_does_not_read_the_row_schema_as_dtypes():
    at = _app(ROW_SCHEMA_SCRIPT)

    assert not at.exception
    assert at.session_state["errors"] == []
    assert at.radio(key="t-editor-mode").value == "Form"
    assert at.session_state["updated"] is None

    at.radio(key="t-editor-mode").set_value("Text Editor")
    at.run()

    assert at.session_state["errors"] == []
    assert at.session_state["updated"] is None


RERENDER_SCRIPT = """
import polars as pl
import streamlit as st
from snakelit.editor.table import form_table

if "frame" not in st.session_state:
    st.session_state["frame"] = pl.DataFrame({"sample": ["a"]})
if "visible" not in st.session_state:
    st.session_state["visible"] = True
errors = []
if st.session_state["visible"]:
    edited = form_table(st.session_state["frame"], errors, key="t")
    st.session_state["edited"] = edited
"""


def test_form_uses_the_current_frame_after_its_editor_closed():
    import polars as pl

    at = _app(RERENDER_SCRIPT)
    assert at.session_state["edited"].to_dict(as_series=False) == {"sample": ["a"]}

    at.session_state["visible"] = False
    at.run()

    at.session_state["frame"] = pl.DataFrame({"sample": ["b"]})
    at.session_state["visible"] = True
    at.run()

    assert at.session_state["edited"].to_dict(as_series=False) == {"sample": ["b"]}


COERCED_SCRIPT = """
import polars as pl
import streamlit as st
from snakelit.editor.table import form_table

SCHEMA = {"type": "object", "properties": {"count": {"type": "integer"}}}
if "frame" not in st.session_state:
    st.session_state["frame"] = pl.DataFrame({"count": ["1"]})
errors = []
edited = form_table(st.session_state["frame"], errors, SCHEMA, key="t")
st.session_state["edited"] = edited
"""


def test_form_table_coerces_before_and_keeps_the_copy_typed():
    import polars as pl

    at = _app(COERCED_SCRIPT)

    assert at.session_state["edited"].schema["count"] == pl.Int64
    assert at.session_state["t-data"].schema["count"] == pl.Int64

    at.run()

    assert at.session_state["edited"].schema["count"] == pl.Int64


def test_drop_empty_rows_drops_only_fully_blank_rows():
    frame = pl.DataFrame(
        {
            "sample": ["a", "", None],
            "count": [1, None, None],
            "tags": [["x"], None, None],
        }
    )

    kept = _drop_empty_rows(frame)

    assert kept.to_dict(as_series=False) == {
        "sample": ["a"],
        "count": [1],
        "tags": [["x"]],
    }
    assert kept.schema == frame.schema
