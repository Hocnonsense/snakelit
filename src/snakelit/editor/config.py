"""Config editors driven by a JSON schema.

``schema_config`` renders a config document as widgets and rebuilds it from the
widget values on every rerun, so it never mutates the caller's object.  The
schema is optional and read-only: with one, widgets and validation follow it;
without one, the config is edited as raw YAML.  Only mappings get the form;
other YAML documents (lists, scalars) fall back to the text editor.  Hosts
discover or let the user choose the schema; nothing in here edits or writes it.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping

import streamlit as st

from ..utils.st_layouts import st_container_maxheight
from ..utils.schema import infer_type, is_schema, property_schema, validate
from ..utils.yaml import SCIENTIFIC_FLOAT, dump as dump_yaml, load
from .text import schema_text_editor


def _dump(data, format: str):
    if format == "yaml":
        return dump_yaml(data)
    from ..utils.json import dump as dump_json

    return dump_json(data)


def _looks_like_path(value: str):
    if not value or "://" in value or any(char.isspace() for char in value):
        return False
    return "/" in value or bool(re.search(r"\.[A-Za-z][A-Za-z0-9]*$", value))


def schema_config(
    data: bytes,
    errors: list[str],
    schema: Mapping[str, Any] | None = None,
    header="Configuration Editor",
    *,
    key: str = "config",
    edit_file: Callable[[str], None] | None = None,
    format: str = "yaml",
):
    """Render an editor for a config file and return the new bytes.

    Widgets follow ``schema`` where it describes a key and are inferred from
    the value elsewhere; a raw YAML editor is always offered as the
    alternative.  ``errors`` is filled in place.  Returns ``None`` when the
    text did not change or is not valid, so the caller can skip writing it.

    With ``edit_file``, a string value that looks like a path gets a button
    that calls it with the path string; the host decides whether to create,
    open or ignore the file.  ``format`` is ``"yaml"`` or ``"json"`` and
    selects the serializer (parsing uses the YAML loader for both).
    """
    text = data.decode("utf-8")
    height = 420
    probe: list[str] = []
    config = load(text, probe)
    if config is None and not probe:
        config = {}

    if isinstance(config, dict):
        mode = st.radio(
            header,
            ["Form", "Text Editor"],
            help="Configuration editor mode",
            horizontal=True,
            key=f"{key}-editor-mode",
        )
        if mode == "Form":
            # Compare canonical YAML, not the source text: comments and
            # formatting must survive an untouched form.
            original = _dump(config, format)
            with st_container_maxheight(f"{key}-form-container", height=height):
                create_form(config, schema, "", key, edit_file)
            before = len(errors)
            errors.extend(validate(config, schema))
            if len(errors) > before:
                return None
            updated = _dump(config, format)
            return None if updated == original else updated.encode("utf-8")

    # Unparseable input is still editable: the text area is the source of
    # truth and reports its own parse/validation errors.
    updated = schema_text_editor(text, schema, key, height=height)
    probe.clear()
    parsed = load(updated, probe)
    if not probe:
        probe.extend(validate(parsed, schema) if parsed else ())
        if not probe:
            return None if updated == text else updated.encode("utf-8")
    errors.extend(probe)


def create_form(
    config: dict,
    schema: Mapping[str, Any] | None,
    path: str = "",
    key: str = "config",
    edit_file: Callable[[str], None] | None = None,
):
    """Render widgets for ``config`` in place, in configuration order.

    Nested mappings recurse into a bordered container at their own position,
    so the form follows the tree instead of collecting them into tabs.  A
    schema entry is used when it exists; otherwise the widget is inferred from
    the value.  No schema is constructed or modified.
    """
    required = set((schema or {}).get("required") or ())

    for name, value in config.items():
        subschema = property_schema(schema, name)
        if isinstance(value, dict):
            with st.container(border=True):
                st.markdown(f"**{name}**")
                if subschema is None or is_schema(subschema):
                    create_form(value, subschema, _path(path, name), key, edit_file)
                else:
                    config[name] = _raw(value, name, f"{key}-{_path(path, name)}", None)
            continue
        config[name] = _value(
            value,
            subschema or infer_type(value),
            _path(path, name),
            key,
            label=name,
            required=name in required,
            edit_file=edit_file,
        )


def _value(
    value,
    schema: Mapping[str, Any],
    path: str,
    key: str,
    *,
    label: str,
    required: bool,
    edit_file: Callable[[str], None] | None = None,
):
    widget_key = f"{key}-{path}"
    help_text = schema.get("description")
    caption = f"{label} *" if required else label
    types = _types(schema)

    if isinstance(schema.get("enum"), list):
        options = list(schema["enum"])
        if value not in options:
            options = [value, *options]
        return st.selectbox(
            caption,
            options,
            index=options.index(value),
            key=widget_key,
            help=help_text,
        )

    if isinstance(value, list):
        return _array(value, schema, caption, widget_key, help_text)

    if isinstance(value, Mapping):
        return _raw(value, caption, widget_key, help_text)

    if "boolean" in types or (not types and isinstance(value, bool)):
        return st.checkbox(caption, value=bool(value), key=widget_key, help=help_text)

    if "integer" in types or "number" in types:
        return _number(value, types, caption, widget_key, help_text)

    if not types and isinstance(value, (int, float)):
        return _number(value, ["number"], caption, widget_key, help_text)

    if "string" in types or not types or value is None:
        return _text(
            value,
            caption,
            widget_key,
            help_text,
            nullable="null" in types,
            edit_file=edit_file,
        )

    return _raw(value, caption, widget_key, help_text)


def _text(
    value,
    caption: str,
    key: str,
    help_text: str | None,
    *,
    nullable: bool,
    edit_file: Callable[[str], None] | None = None,
):
    text = "" if value is None else str(value)
    if edit_file is None or not _looks_like_path(text):
        edited = st.text_input(caption, value=text, key=key, help=help_text)
    else:
        field, action = st.columns([5, 1], vertical_alignment="bottom")
        edited = field.text_input(caption, value=text, key=key, help=help_text)
        action.button(
            "Edit",
            key=f"{key}-file",
            help=f"Treat `{text}` as a file, and open to edit it",
            on_click=edit_file,
            args=(edited or text,),
        )
    if nullable and not edited.strip():
        return None
    return edited


def _number(value, types: list[str], caption: str, key: str, help_text: str | None):
    # Scientific-notation floats are strings by convention and must stay so.
    if isinstance(value, str) or value is None or not types:
        text = "" if value is None else str(value)
        edited = st.text_input(caption, value=text, key=key, help=help_text)
        return _parse_number(edited)

    integer = "integer" in types
    number = int(value) if integer else float(value)
    edited = st.number_input(
        caption,
        value=number,
        step=1 if integer else 0.1,
        key=key,
        help=help_text,
        format="%d" if integer else None,
    )
    if edited == value:
        # preserve the original object: an int must not become 2.0 just because
        # the schema allows any number
        return value
    if not integer and isinstance(value, int) and float(edited).is_integer():
        return int(edited)
    return edited


def _parse_number(text: str):
    stripped = text.strip()
    if not stripped:
        return None
    if SCIENTIFIC_FLOAT.match(stripped):
        return stripped
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        return stripped


def _array(
    value: list,
    schema: Mapping[str, Any],
    caption: str,
    key: str,
    help_text: str | None,
):
    items = schema.get("items") or {}
    if not isinstance(value, list):
        value = [] if value is None else [value]

    if (
        is_schema(items)
        or "array" in _types(items)
        or any(isinstance(item, (Mapping, list)) for item in value)
    ):
        parsed = _raw(value, caption, key, help_text)
        return parsed if isinstance(parsed, list) else value

    text = "\n".join("" if item is None else str(item) for item in value)
    edited = st.text_area(
        f"{caption} (one value per line)",
        value=text,
        key=key,
        help=help_text,
        height=min(200, 40 + 22 * max(1, len(value))),
    )
    parsed = []
    for line in edited.splitlines():
        if not line.strip():
            continue
        try:
            item = load(line)
        except Exception:  # noqa: BLE001 - shown to the user
            st.error(f"Invalid value in {caption}: {line!r}")
            return value
        parsed.append(line.strip() if isinstance(item, (dict, list)) else item)
    return parsed


def _raw(value, caption: str, key: str, help_text: str | None):
    edited = st.text_area(
        f"{caption} (YAML)",
        value=dump_yaml(value),
        key=key,
        help=help_text,
        height=160,
    )
    errors = []
    parsed = load(edited, errors)
    if errors:
        st.error(errors[0])
        return value
    return parsed


def _types(schema: Mapping[str, Any]) -> list[str]:
    declared = schema.get("type")
    if isinstance(declared, str):
        return [declared]
    return list(declared or ())


def _path(parent: str, name: str):
    return f"{parent}.{name}" if parent else name
