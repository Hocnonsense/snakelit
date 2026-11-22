"""Form and text editing for schema-backed configuration and table files."""

from collections.abc import Callable, Iterable, Mapping

import streamlit as st

from ..utils import yaml
from ..utils.st_layouts import st_container_maxheight
from .text import text_editor


def schema_editor(
    data: bytes,
    errors: list[str],
    schema: Mapping | None,
    header: str,
    *,
    key: str,
    format: str,
    can_text: bool,
    render_form: Callable[[list[str]], bytes | None] | None,
    validate: Callable[[bytes, Mapping | None], Iterable[str]],
):
    """Validate the candidate file, or the original file when unchanged."""
    modes = []
    if render_form is not None:
        modes.append("Form")
    if can_text:
        modes.append("Text Editor")
    if not modes:
        raise ValueError("No form or text editor available for the file.")
    mode = modes[0]
    height = 420
    show_schema = False
    if len(modes) > 1 or schema is not None:
        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="bottom",
        ):
            if len(modes) > 1:
                mode = st.radio(
                    header, modes, horizontal=True, key=f"{key}-editor-mode"
                )
            if schema is not None:
                show_schema = st.toggle("View schema", key=f"{key}-show-schema")

    # Keep the editor in the first column when toggling the reference pane.
    columns = st.columns([3, 2] if show_schema else [1])
    if show_schema:
        columns[1].code(yaml.dump(schema), language="yaml", height=height)
    problems: list[str] = []
    with columns[0]:
        if mode == "Form":
            assert render_form is not None
            with st_container_maxheight(f"{key}-form-container", height=height):
                candidate = render_form(problems)
        else:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                errors.append(f"Cannot edit {format.upper()} data as text.")
                return None
            updated = text_editor(text, key, height=height, language=format)
            candidate = None if updated == text else updated.encode("utf-8")

    if not problems:
        problems.extend(validate(data if candidate is None else candidate, schema))
    errors.extend(problems)
    return None if problems else candidate
