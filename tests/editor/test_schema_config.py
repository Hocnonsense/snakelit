"""Widget-level tests for the schema-driven mapping editor."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from streamlit.testing.v1 import AppTest  # noqa: E402

SCRIPT = """
import streamlit as st
from snakelit.editor.config import schema_config
from snakelit.utils import yaml

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
updated = schema_config(yaml.dump(CONFIG).encode(), errors, SCHEMA, key="cfg")
st.session_state["updated"] = updated
st.session_state["errors"] = errors
st.session_state["edited"] = (
    yaml.load(updated.decode()) if updated is not None else CONFIG
)
"""


@pytest.fixture
def native_text_editor(monkeypatch):
    """Exercise the editable text-area fallback through AppTest."""
    monkeypatch.setitem(sys.modules, "streamlit_ace", None)


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


def test_text_mode_shows_the_schema_read_only(native_text_editor):
    at = _app()
    assert not at.code
    at.toggle(key="cfg-show-schema").set_value(True).run()
    assert any("properties" in item.value for item in at.code)
    _by_key(at.radio, "cfg-editor-mode").set_value("Text Editor")
    at.run()

    assert not at.exception, [str(error.value) for error in at.exception]
    assert "samples: samples.tsv" in (_by_key(at.text_area, "cfg-editor").value or "")
    assert any("properties" in (item.value or "") for item in at.code)


def test_text_mode_is_validated_against_the_schema(native_text_editor):
    at = _app()
    _by_key(at.radio, "cfg-editor-mode").set_value("Text Editor")
    at.run()
    _by_key(at.text_area, "cfg-editor").set_value("samples: ''\n")
    at.run()

    assert "samples: required value is empty" in at.session_state["errors"]
    assert at.session_state["updated"] is None
    assert at.session_state["edited"]["samples"] == "samples.tsv"


def test_text_mode_returns_no_text_on_invalid_yaml(native_text_editor):
    at = _app()
    _by_key(at.radio, "cfg-editor-mode").set_value("Text Editor")
    at.run()
    _by_key(at.text_area, "cfg-editor").set_value("samples: [\n")
    at.run()

    assert at.session_state["errors"]
    assert at.session_state["updated"] is None


RAW_SCRIPT = """
import streamlit as st
from snakelit.editor.config import schema_config
from snakelit.utils import yaml

CONFIG = {"a": 1}

errors = []
updated = schema_config(yaml.dump(CONFIG).encode(), errors, None, key="raw")
st.session_state["updated"] = updated
st.session_state["errors"] = errors
st.session_state["edited"] = (
    yaml.load(updated.decode()) if updated is not None else CONFIG
)
"""


def test_without_schema_infers_a_form_from_the_config():
    at = _app(RAW_SCRIPT)

    assert not at.exception, [str(error.value) for error in at.exception]
    assert _by_key(at.number_input, "raw-a").value == 1


def test_invalid_raw_yaml_returns_no_text(native_text_editor):
    at = _app(RAW_SCRIPT)
    _by_key(at.radio, "raw-editor-mode").set_value("Text Editor")
    at.run()
    _by_key(at.text_area, "raw-editor").set_value("a: [\n")
    at.run()

    assert at.session_state["errors"]
    assert at.session_state["updated"] is None


BROKEN_SCRIPT = """
import streamlit as st
from snakelit.editor.config import schema_config

errors = []
updated = schema_config(b"a: [\\n", errors, None, key="broken")
st.session_state["updated"] = updated
st.session_state["errors"] = errors
"""


def test_broken_text_opens_in_the_text_editor_and_can_be_repaired(native_text_editor):
    at = _app(BROKEN_SCRIPT)

    assert [item.key for item in at.radio] == []
    editor = _by_key(at.text_area, "broken-editor")
    assert editor.value == "a: [\n"

    editor.set_value("a: 2\n")
    at.run()

    assert at.session_state["errors"] == []
    assert at.session_state["updated"] == b"a: 2\n"


FILE_SCRIPT = """
import streamlit as st
from snakelit.editor.config import schema_config

if "clicked" not in st.session_state:
    st.session_state["clicked"] = []
errors = []
schema_config(
    b"samples: config/samples.tsv\\nmode: fast\\n",
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


def test_nested_mappings_render_as_tabs():
    at = _app()

    assert not at.exception
    assert "params" in [tab.label for tab in at.tabs]


def test_string_list_keeps_yaml_looking_values_after_an_edit():
    at = _app(
        SCRIPT.replace('"values": [1, 2]', '"values": ["001", "true"]').replace(
            '"items": {"type": "integer"}', '"items": {"type": "string"}'
        )
    )
    assert at.session_state["updated"] is None
    _by_key(at.text_area, "cfg-values").set_value("001\ntrue\n001")
    at.run()
    assert at.session_state["edited"]["values"] == ["001", "true", "001"]


def test_form_preserves_untouched_yaml_bytes():
    script = RAW_SCRIPT.replace(
        "yaml.dump(CONFIG).encode()", "b'# comment\\na: 1  # unit\\n'"
    )
    assert _app(script).session_state["updated"] is None


def test_form_writes_changed_json_as_json():
    import json

    script = RAW_SCRIPT.replace(
        "yaml.dump(CONFIG).encode()", """b'{"a": 1}'"""
    ).replace('key="raw"', 'key="raw", format="json"')
    at = _app(script)
    assert at.session_state["updated"] is None
    at.number_input(key="raw-a").set_value(3).run()
    assert json.loads(at.session_state["updated"]) == {"a": 3}


def test_clearing_valid_text_returns_empty_bytes(native_text_editor):
    at = _app(RAW_SCRIPT)
    at.radio(key="raw-editor-mode").set_value("Text Editor").run()
    at.text_area(key="raw-editor").set_value("").run()
    assert not at.exception
    assert at.session_state["errors"] == []
    assert at.session_state["updated"] == b""


def test_text_mode_returns_original_formatting_with_the_edit(native_text_editor):
    at = _app(RAW_SCRIPT)
    at.radio(key="raw-editor-mode").set_value("Text Editor").run()
    text = "# unit\na: 2  # count\n"
    at.text_area(key="raw-editor").set_value(text).run()
    assert at.session_state["updated"] == text.encode()
    assert at.session_state["errors"] == []


def test_invalid_field_blocks_other_form_changes():
    at = _app()
    at.text_area(key="cfg-values").set_value("[")
    at.number_input(key="cfg-threads").set_value(7).run()
    assert not at.exception
    assert at.session_state["errors"]
    assert at.session_state["updated"] is None


def test_yaml_null_is_validated_as_a_value(native_text_editor):
    at = _app()
    at.radio(key="cfg-editor-mode").set_value("Text Editor").run()
    at.text_area(key="cfg-editor").set_value("null").run()
    assert not at.exception
    assert at.session_state["errors"]
    assert at.session_state["updated"] is None


def _root_app(source, schema=None, format="yaml"):
    return _app(f"""
import streamlit as st
from snakelit.editor.config import schema_config
errors = []
st.session_state.updated = schema_config({source!r}, errors, {schema!r}, key="root", format={format!r})
st.session_state.errors = errors
""")


def test_float_root_is_editable_without_rewriting_untouched_yaml():
    from snakelit.utils import yaml

    at = _root_app(b"0.50 # threshold")
    assert not at.exception
    assert at.radio[0].value == "Form"
    assert at.session_state.updated is None
    at.number_input[0].set_value(0.8).run()
    assert yaml.load(at.session_state["updated"].decode("utf-8")) == 0.8


def test_list_root_writes_a_json_array_and_validates_items():
    from snakelit.utils import yaml

    at = _root_app(b"[1, 2]", {"type": "array", "items": {"type": "integer"}}, "json")
    assert at.session_state.updated is None
    at.text_area[0].set_value("3\n4").run()
    assert yaml.load(at.session_state["updated"].decode("utf-8")) == [3, 4]
    at.text_area[0].set_value("3\nwrong").run()
    assert at.session_state.errors
    assert at.session_state.updated is None


def test_scalar_root_schema_mismatch_does_not_change_the_value():
    at = _root_app(b"0.5", {"type": "object"})
    assert at.number_input[0].value == 0.5
    assert at.session_state.errors
    assert at.session_state.updated is None
