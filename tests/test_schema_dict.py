"""Widget-level tests for the schema-driven mapping editor."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamlit.testing.v1 import AppTest  # noqa: E402

SCRIPT = """
import streamlit as st
from snakelit.editors import schema_dict
from snakelit.utils.yaml import dump, load

CONFIG = {
    "samples": "samples.tsv",
    "threads": 4,
    "mode": "fast",
    "values": [1, 2],
    "params": {"alpha": 0.5, "enabled": True},
}
SCHEMA = {
    "type": "object",
    "required": ["samples"],
    "properties": {
        "samples": {"type": "string", "description": "Sample sheet"},
        "threads": {"type": "integer"},
        "mode": {"enum": ["fast", "slow"]},
        "values": {"type": "array", "items": {"type": "integer"}},
        "params": {
            "type": "object",
            "properties": {
                "alpha": {"type": "number"},
                "enabled": {"type": "boolean"},
            },
        },
        "optional": {"type": "string", "default": "x"},
    },
}

errors = []
updated = schema_dict(dump(CONFIG), errors, SCHEMA, key="cfg")
st.session_state["updated"] = updated
st.session_state["errors"] = errors
st.session_state["edited"] = load(updated) if updated is not None else CONFIG
"""


def _app(script=SCRIPT):
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    return at


def _by_key(items, key):
    return next(item for item in items if item.key == key)


def test_renders_one_widget_per_property():
    at = _app()

    assert not at.exception, [str(error.value) for error in at.exception]
    assert _by_key(at.text_input, "cfg-samples").value == "samples.tsv"
    assert _by_key(at.number_input, "cfg-threads").value == 4
    assert _by_key(at.selectbox, "cfg-mode").value == "fast"
    assert _by_key(at.text_area, "cfg-values").value == "1\n2"
    assert _by_key(at.number_input, "cfg-params.alpha").value == 0.5
    assert _by_key(at.checkbox, "cfg-params.enabled").value is True
    assert at.session_state["errors"] == []


def test_edits_are_rebuilt_into_the_config():
    at = _app()
    _by_key(at.text_input, "cfg-samples").set_value("other.tsv")
    _by_key(at.number_input, "cfg-threads").set_value(8)
    _by_key(at.selectbox, "cfg-mode").set_value("slow")
    _by_key(at.text_area, "cfg-values").set_value("3\n4")
    _by_key(at.number_input, "cfg-params.alpha").set_value(0.25)
    at.run()

    edited = at.session_state["edited"]
    assert edited["samples"] == "other.tsv"
    assert edited["threads"] == 8
    assert edited["mode"] == "slow"
    assert edited["values"] == [3, 4]
    assert edited["params"]["alpha"] == 0.25


def test_missing_required_value_is_reported():
    at = _app()
    _by_key(at.text_input, "cfg-samples").set_value("")
    at.run()

    assert "samples: required value is empty" in at.session_state["errors"]
    assert at.session_state["updated"] is None


def test_unknown_keys_are_preserved():
    at = _app(SCRIPT.replace('"mode": "fast",', '"mode": "fast", "extra": 7,'))

    assert _by_key(at.number_input, "cfg-extra").value == 7
    assert at.session_state["edited"]["extra"] == 7


def test_nested_unknown_keys_get_inferred_widgets():
    at = _app(SCRIPT.replace('"alpha": 0.5,', '"alpha": 0.5, "beta": "b",'))

    assert _by_key(at.text_input, "cfg-params.beta").value == "b"
    assert at.session_state["edited"]["params"]["beta"] == "b"


def test_unknown_keys_are_not_validated():
    at = _app(SCRIPT.replace('"mode": "fast",', '"mode": "fast", "extra": [],'))

    assert at.session_state["errors"] == []
    assert at.session_state["edited"]["extra"] == []


def test_integer_value_stays_integer_for_number_schema():
    at = _app(
        SCRIPT.replace('"threads": 4,', '"threads": 4, "ratio": 2,').replace(
            '"threads": {"type": "integer"},',
            '"threads": {"type": "integer"}, "ratio": {"type": "number"},',
        )
    )

    assert at.session_state["updated"] is None
    assert at.session_state["edited"]["ratio"] == 2


def test_scientific_float_stays_text():
    at = _app(
        SCRIPT.replace('"threads": 4,', '"threads": 4, "threshold": "1e-5",').replace(
            '"threads": {"type": "integer"},',
            '"threads": {"type": "integer"}, "threshold": {"type": "number"},',
        )
    )

    assert _by_key(at.text_input, "cfg-threshold").value == "1e-5"
    assert at.session_state["edited"]["threshold"] == "1e-5"


def test_text_mode_shows_the_schema_read_only():
    at = _app()
    _by_key(at.radio, "cfg-editor-mode").set_value("Text Editor")
    at.run()

    assert not at.exception, [str(error.value) for error in at.exception]
    assert "samples: samples.tsv" in (_by_key(at.text_area, "cfg-editor").value or "")
    assert any("properties" in (item.value or "") for item in at.code)


def test_text_mode_is_validated_against_the_schema():
    at = _app()
    _by_key(at.radio, "cfg-editor-mode").set_value("Text Editor")
    at.run()
    _by_key(at.text_area, "cfg-editor").set_value("samples: ''\n")
    at.run()

    assert "samples: required value is empty" in at.session_state["errors"]
    assert at.session_state["updated"] is None
    assert at.session_state["edited"]["samples"] == "samples.tsv"


def test_text_mode_returns_no_text_on_invalid_yaml():
    at = _app()
    _by_key(at.radio, "cfg-editor-mode").set_value("Text Editor")
    at.run()
    _by_key(at.text_area, "cfg-editor").set_value("samples: [\n")
    at.run()

    assert at.session_state["errors"]
    assert at.session_state["updated"] is None


RAW_SCRIPT = """
import streamlit as st
from snakelit.editors import schema_dict
from snakelit.utils.yaml import dump, load

CONFIG = {"a": 1}

errors = []
updated = schema_dict(dump(CONFIG), errors, None, key="raw")
st.session_state["updated"] = updated
st.session_state["errors"] = errors
st.session_state["edited"] = load(updated) if updated is not None else CONFIG
"""


def test_without_schema_infers_a_form_from_the_config():
    at = _app(RAW_SCRIPT)

    assert not at.exception, [str(error.value) for error in at.exception]
    assert _by_key(at.number_input, "raw-a").value == 1


def test_invalid_raw_yaml_returns_no_text():
    at = _app(RAW_SCRIPT)
    _by_key(at.radio, "raw-editor-mode").set_value("Text Editor")
    at.run()
    _by_key(at.text_area, "raw-editor").set_value("a: [\n")
    at.run()

    assert at.session_state["errors"]
    assert at.session_state["updated"] is None


BROKEN_SCRIPT = """
import streamlit as st
from snakelit.editors import schema_dict

errors = []
updated = schema_dict("a: [\\n", errors, None, key="broken")
st.session_state["updated"] = updated
st.session_state["errors"] = errors
"""


def test_broken_text_opens_in_the_text_editor_and_can_be_repaired():
    at = _app(BROKEN_SCRIPT)

    assert [item.key for item in at.radio] == []
    editor = _by_key(at.text_area, "broken-editor")
    assert editor.value == "a: [\n"

    editor.set_value("a: 2\n")
    at.run()

    assert at.session_state["errors"] == []
    assert at.session_state["updated"] == "a: 2\n"


FILE_SCRIPT = """
import streamlit as st
from snakelit.editors import schema_dict

if "clicked" not in st.session_state:
    st.session_state["clicked"] = []
errors = []
schema_dict(
    "samples: config/samples.tsv\\nmode: fast\\n",
    errors,
    {
        "type": "object",
        "properties": {"samples": {"type": "string"}, "mode": {"type": "string"}},
    },
    key="f",
    edit_file=st.session_state["clicked"].append,
)
"""


def test_path_values_get_a_file_button_that_reports_the_path():
    at = _app(FILE_SCRIPT)

    edit = _by_key(at.button, "f-samples-file")
    assert edit.label == "Edit"
    assert not any(item.key == "f-mode-file" for item in at.button)

    edit.click()
    at.run()

    assert at.session_state["clicked"] == ["config/samples.tsv"]
