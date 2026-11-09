"""Editable Polars-backed table widgets.

``form_table`` seeds ``st.data_editor`` from the frame it is given; the
editor's widget state carries the edits, and the caller decides where the
returned frame goes.  ``column_controls`` renders icon add/rename/remove/move
popovers that replace the frame before it is edited.  ``schema_table`` adds
optional row-schema coercion and validation on top of a bytes value.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import polars as pl
import streamlit as st

from .table_schema import coerce_frame, table_errors
from .text import schema_text_editor
from ..utils.table import dump, load
from ..utils.st_layouts import st_container_maxheight

Control = Callable[[str, pl.DataFrame], tuple[pl.DataFrame, Any] | None]
"""A control returns ``(frame, payload)`` when it fired, else ``None``."""


def schema_table(
    data: bytes,
    errors: list[str],
    schema: Mapping[str, Any] | None = None,
    header: str = "Table Editor",
    *,
    key: str = "table",
    format: str = "csv",
):
    """Render an editor for a table and return the new bytes.

    ``format`` is the table's file suffix (``csv``, ``tsv``, ``parquet`` or
    ``xlsx``).  Text formats offer a Form/Text switch, binary formats only the
    form.  ``errors`` is filled in place.  Returns ``None`` when the data did
    not change or is invalid, so the caller can skip writing it.

    With ``schema``, the form coerces columns to its declared dtypes and
    validates every row; the schema is never edited.
    """
    height = 420
    # A file that cannot be read is not an error yet: the text editor takes
    # over below, so this probe keeps its failures to itself.
    table = load(data, suffix=format, errors=[])
    textable = format in ("csv", "tsv")
    if table is not None:
        if (
            not textable
            or st.radio(
                header,
                ["Form", "Text Editor"],
                help="Table editor mode",
                horizontal=True,
                key=f"{key}-editor-mode",
            )
            == "Form"
        ):
            before = len(errors)
            with st_container_maxheight(f"{key}-form-container", height=height):
                edited = form_table(table, errors, schema, key=key)
            if len(errors) > before:
                return None
            # Compare canonical bytes: coercion changes dtypes without changing
            # the values, and an untouched form must not rewrite the table.
            updated = dump(edited, format)
            return None if updated == dump(table, format) else updated
    elif not textable:
        st.error(f"Cannot edit broken {format.upper()} table as text.")
        return None

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        st.error(f"Cannot edit {format.upper()} data as text.")
        return None
    updated = schema_text_editor(text, schema, key, height=height)
    before = len(errors)
    parsed = load(updated.encode("utf-8"), suffix=format, errors=errors)
    if parsed is None:
        return None
    if schema:
        parsed, _ = coerce_frame(parsed, schema, errors)
    errors.extend(table_errors(parsed, schema))
    if len(errors) > before:
        return None
    return None if updated == text else updated.encode("utf-8")


def form_table(
    frame: pl.DataFrame,
    errors: list[str],
    schema: Mapping | None = None,
    *,
    key: str = "table",
    column_config: Mapping | None = None,
):
    """Edit ``frame`` and return the edited frame.

    With ``schema``, cells carry its declared dtypes and every row is validated;
    the schema itself is never edited.
    """
    data_key = f"{key}-data"
    if schema:
        # input frame is loaded without schema (default strings for csv/tsv),
        # so coerce it to the schema before comparing.
        frame, _ = coerce_frame(frame, schema, errors)

    current: pl.DataFrame | None = st.session_state.get(data_key)
    if current is None or not current.equals(frame):
        # The host's frame is the truth: refresh the copy whenever it changed,
        # so an unmounted editor or a document changed elsewhere cannot leave
        # stale rows behind.
        st.session_state[data_key] = frame
    column_controls(key)
    edited = editable_table(key, column_config=column_config)

    if schema:
        # strip and format the edited frame to save correctly.
        edited, _ = coerce_frame(edited, schema, errors)
        st.session_state[data_key] = edited
        errors.extend(table_errors(edited, schema))
    return edited


def column_controls(
    key: str,
    *,
    controls: Mapping[str, Control] | None = None,
    extras: Mapping[str, Control] | None = None,
):
    """Render column popovers for ``st.session_state[f"{key}-data"]``.

    Returns the changes applied, keyed by control name.  ``controls`` replaces
    the default add/rename/remove/move set; ``extras`` renders more next to it.
    """
    changes: dict[str, Any] = {}
    calls = dict(controls or _default_controls) | dict(extras or {})
    holders = st.columns(len(calls))
    for holder, call in zip(holders, calls):
        with holder:
            ret = calls[call](key, st.session_state[f"{key}-data"])
        if ret is not None:
            st.session_state[f"{key}-data"], changes[call] = ret
    return changes


def editable_table(
    key: str,
    *,
    column_config: Mapping | None = None,
    drop_empty: bool = True,
) -> pl.DataFrame:
    """Render ``st.data_editor`` for ``st.session_state[f"{key}-data"]``.

    The editor is seeded from that copy every run; its widget state carries the
    edits and the result is written back to the copy.
    """
    data_key = f"{key}-data"
    edited = st.data_editor(
        st.session_state[data_key].to_pandas(),
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key=f"{key}-editor",
        column_config=column_config,
    )
    result = pl.from_pandas(edited)
    result = _drop_empty_rows(result) if drop_empty else result
    st.session_state[data_key] = result
    return result


def _drop_empty_rows(frame: pl.DataFrame):
    """Drop rows where every cell is null or blank."""
    if frame.height == 0 or not frame.columns:
        return frame
    blank = [
        pl.col(column).is_null()
        | (pl.col(column).cast(pl.Utf8).str.strip_chars() == "")
        for column in frame.columns
    ]
    return frame.filter(~pl.all_horizontal(blank))


def _add_column(key: str, frame: pl.DataFrame):
    options = list(frame.columns)
    with st.popover("", icon=":material/add:", help="Add a column"):
        name = st.text_input("Add column", key=f"{key}-new-column")
        clicked = st.button("Add", key=f"{key}-add-column")
    name = (name or "").strip()
    if clicked and name and name not in options:
        return frame.with_columns(pl.Series(name, [""] * frame.height)), name


def _rename_column(key: str, frame: pl.DataFrame):
    options = list(frame.columns)
    with st.popover("", icon=":material/edit:", help="Rename a column"):
        if options:
            selected = st.selectbox(
                "Select column to rename", options, key=f"{key}-rename-column"
            )
            renamed = st.text_input("Rename to", key=f"{key}-rename-column-text")
            clicked = st.button("Rename", key=f"{key}-rename-column-button")
        else:
            st.caption("No columns to rename.")
            selected, renamed, clicked = None, "", False
    new_name = (renamed or "").strip()
    if clicked and new_name and new_name not in options and selected in frame.columns:
        return frame.rename({selected: new_name}), (selected, new_name)


def _delete_column(key: str, frame: pl.DataFrame):
    options = list(frame.columns)
    with st.popover("", icon=":material/remove:", help="Remove a column"):
        if options:
            selected = st.selectbox(
                "Select column to remove", options, key=f"{key}-remove-column"
            )
            clicked = st.button("Remove", key=f"{key}-remove-column-button")
        else:
            st.caption("No columns to remove.")
            selected, clicked = None, False
    if clicked and selected in frame.columns:
        return frame.drop(selected), selected


def _move_column(key: str, frame: pl.DataFrame):
    options = list(frame.columns)
    with st.popover("", icon=":material/swap_horiz:", help="Reorder columns"):
        if len(options) > 1:
            selected = st.selectbox("Move column", options, key=f"{key}-move-column")
            target = st.selectbox(
                "Move before", ["(end)", *options], key=f"{key}-move-target"
            )
            clicked = st.button("Move", key=f"{key}-move-button")
        else:
            st.caption("Need at least two columns to reorder.")
            return None
    if not clicked or selected not in options:
        return None
    order = [column for column in options if column != selected]
    index = len(order) if target == "(end)" else order.index(target)
    order.insert(index, selected)
    if order == options:
        return None
    return frame.select(order), order


_default_controls = {
    "add": _add_column,
    "rename": _rename_column,
    "remove": _delete_column,
    "move": _move_column,
}
