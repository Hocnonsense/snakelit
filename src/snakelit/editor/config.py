"""Shared workflow config form and raw text editor."""

from __future__ import annotations

import math
import re
from typing import Any, Callable, Mapping

import streamlit as st

try:
    from streamlit_tags import st_tags
except ModuleNotFoundError as error:
    if error.name != "streamlit_tags":
        raise
    st_tags = None

from ..utils.schema import infer_type, is_schema, property_schema, validate
from ..utils import json, yaml
from .schema import schema_editor


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
    format: str = "yaml",
    edit_file: Callable[[str], None] | None = None,
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
    dump = (yaml if format == "yaml" else json).dump
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        errors.append(str(error))
        return None
    probe: list[str] = []
    config = yaml.load(text, probe)
    if config is None and not probe and not text.strip():
        config = {}

    can_render_form = not probe and isinstance(config, (dict, list, str, int, float))
    # Streamlit numeric inputs must round-trip through a JavaScript number.
    if isinstance(config, int) and abs(config) > 2**53 - 1:
        can_render_form = False
    elif isinstance(config, float) and not math.isfinite(config):
        can_render_form = False

    def render_form(problems: list[str]) -> bytes | None:
        original = dump(config)
        if isinstance(config, dict):
            create_form(
                config, schema, "", key_prefix=key, edit_file=edit_file, errors=problems
            )
            edited = config
        else:
            # Render an incompatible root as its actual type. Validation can then
            # report the mismatch without the widget silently coercing the value.
            inferred = infer_type(config)
            field_schema = {**inferred, **(schema or {})}
            types = _types(field_schema)
            if len(types) != 1 or (
                inferred["type"] not in types
                and not (inferred["type"] == "integer" and types == ["number"])
            ):
                field_schema["type"] = inferred["type"]
            edited = get_input_element(
                "Value",
                config,
                field_schema,
                f"{key}:root",
                required=False,
                edit_file=edit_file,
                errors=problems,
            )
        if problems:
            return None
        updated = dump(edited)
        if updated == original or updated == text:
            return None
        return updated.encode("utf-8")

    def validate_config(contents: bytes, schema: Mapping | None):
        problems: list[str] = []
        parsed = yaml.load(contents.decode("utf-8"), problems)
        if not problems:
            problems.extend(validate(parsed, schema))
        return problems

    return schema_editor(
        data,
        errors,
        schema,
        header,
        key=key,
        format=format,
        can_text=True,
        render_form=render_form if can_render_form else None,
        validate=validate_config,
    )


# The form traversal and field controls originate in SRPtn's config_editor.py.
def create_form(
    config: dict,
    schema: Mapping[str, Any] | None,
    parent_key: str = "",
    *,
    key_prefix: str = "config",
    edit_file: Callable[[str], None] | None = None,
    errors: list[str] | None = None,
):
    """Render the config in place, using a separate widget namespace per editor."""
    required_fields = (schema or {}).get("required", [])
    new_tabs = []
    for key, value in config.items():
        unique_element_id = update_key(parent_key, key)
        input_dict = property_schema(schema, key)
        if not isinstance(value, dict):
            config[key] = get_input_element(
                key,
                value,
                input_dict or infer_type(value),
                f"{key_prefix}-{unique_element_id}",
                required=key in required_fields,
                edit_file=edit_file,
                errors=errors,
            )
        elif input_dict is not None and not is_schema(input_dict):
            config[key] = _raw(
                value, key, f"{key_prefix}-{unique_element_id}", None, errors
            )
        else:
            new_tabs.append((key, value))

    if new_tabs:
        tabs = st.tabs([key for key, _ in new_tabs])
        for tab, (key, value) in enumerate(new_tabs):
            updated_parent_key = update_key(parent_key, key)
            new_schema = property_schema(schema, key)
            with tabs[tab]:
                create_form(
                    value,
                    new_schema,
                    updated_parent_key,
                    key_prefix=key_prefix,
                    edit_file=edit_file,
                    errors=errors,
                )


def get_input_element(
    label: str,
    value,
    input_dict: Mapping[str, Any],
    key: str,
    *,
    required: bool,
    edit_file: Callable[[str], None] | None,
    errors: list[str] | None = None,
):
    """Render a field and return its value to the caller's config."""
    help_text = input_dict.get("description")
    caption = f"{label} *" if required else label
    types = _types(input_dict)

    if isinstance(input_dict.get("enum"), list):
        options = list(input_dict["enum"])
        if value not in options:
            options = [value, *options]
        return st.selectbox(
            caption,
            options,
            index=options.index(value),
            key=key,
            help=help_text,
        )

    if isinstance(value, list):
        return _array(value, input_dict, caption, key, help_text, errors)

    if isinstance(value, Mapping):
        return _raw(value, caption, key, help_text, errors)

    if "boolean" in types or (not types and isinstance(value, bool)):
        return st.checkbox(caption, value=bool(value), key=key, help=help_text)

    if "integer" in types or "number" in types:
        return _number(value, types, caption, key, help_text)

    if not types and isinstance(value, (int, float)):
        return _number(value, ["number"], caption, key, help_text)

    if "string" in types or not types or value is None:
        return _text(
            value,
            caption,
            key,
            help_text,
            nullable="null" in types,
            edit_file=edit_file,
        )

    return _raw(value, caption, key, help_text, errors)


def handle_string_input(
    label: str,
    value: str,
    key: str,
    *,
    help_text: str | None = None,
):
    """Handle input for string types."""
    return st.text_input(label=label, value=value, key=key, help=help_text)


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
        edited = handle_string_input(caption, text, key, help_text=help_text)
    else:
        field, action = st.columns([5, 1], vertical_alignment="bottom")
        with field:
            edited = handle_string_input(caption, text, key, help_text=help_text)
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
        edited = handle_string_input(caption, text, key, help_text=help_text)
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
    if yaml.SCIENTIFIC_FLOAT.match(stripped):
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
    errors: list[str] | None,
):
    items = schema.get("items") or {}
    if not isinstance(value, list):
        value = [] if value is None else [value]

    string_items = _types(items) == ["string"] and all(
        isinstance(item, str) for item in value
    )
    if (
        st_tags is not None
        and string_items
        and schema.get("uniqueItems")
        and len(set(value)) == len(value)
    ):
        return handle_array_input(caption, value, key)

    if (
        any(
            item is None
            or isinstance(item, str)
            and (not item or "\n" in item or "\r" in item)
            for item in value
        )
        or (any(isinstance(item, str) for item in value) and not string_items)
        or is_schema(items)
        or "array" in _types(items)
        or any(isinstance(item, (Mapping, list)) for item in value)
    ):
        parsed = _raw(value, caption, key, help_text, errors)
        if not isinstance(parsed, list):
            _field_error(f"{caption}: expected a list", errors)
            return value
        return parsed

    text = "\n".join("" if item is None else str(item) for item in value)
    edited = st.text_area(
        f"{caption} (one value per line)",
        value=text,
        key=key,
        help=help_text,
        height=min(200, 40 + 22 * max(1, len(value))),
    )
    if edited == text:
        return value
    if string_items:
        return edited.splitlines()
    parsed = []
    for line in edited.splitlines():
        if not line.strip():
            continue
        try:
            item = yaml.load(line)
        except Exception:  # noqa: BLE001 - shown to the user
            _field_error(f"Invalid value in {caption}: {line!r}", errors)
            return value
        parsed.append(line.strip() if isinstance(item, (dict, list)) else item)
    return parsed


def _field_error(message: str, errors: list[str] | None):
    if errors is None:
        st.error(message)
    else:
        errors.append(message)


def _raw(
    value, caption: str, key: str, help_text: str | None, errors: list[str] | None
):
    edited = st.text_area(
        f"{caption} (YAML)",
        value=yaml.dump(value),
        key=key,
        help=help_text,
        height=160,
    )
    problems = []
    parsed = yaml.load(edited, problems)
    if problems:
        _field_error(f"{caption}: {problems[0]}", errors)
        return value
    return parsed


def _types(schema: Mapping[str, Any]) -> list[str]:
    declared = schema.get("type")
    if isinstance(declared, str):
        return [declared]
    return list(declared or ())


def handle_array_input(label: str, value, key: str):
    """Handle input for array types."""
    # cannot differentiate type here ~ no way to represent array of ints or floats except stringified
    if not isinstance(value, list):
        value = [value]
    assert st_tags is not None, "streamlit_tags is not installed"
    return st_tags(label=label, value=value, key=key)


def update_key(parent_key: str, new_key: str):
    """Append a new key to an existing parent key, forming a dot-separated string.

    :param parent_key: The existing key string.
    :param new_key: The new key to append.
    :return: The concatenated key string.
    """
    return f"{parent_key}.{new_key}" if parent_key != "" else new_key
