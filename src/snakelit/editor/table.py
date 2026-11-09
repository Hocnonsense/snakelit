"""Editable Polars-backed table widgets.

A table is identified by ``key``; its current data lives in
``st.session_state[f"{key}-data"]``.  ``column_controls`` renders icon
add/rename/remove/reorder popovers that edit that entry; ``editable_table``
wraps ``st.data_editor`` and returns the edited frame.  ``schema_table`` adds
optional row-schema coercion and validation.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import polars as pl
import streamlit as st

from .table_schema import coerce_frame, table_errors
from .text import schema_text_editor
from ..utils.table import read, dump
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
    table = read(data, suffix=format, schema=schema)
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
            if len(errors) > before or edited.equals(table):
                return None
            return dump(edited, format)
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
    parsed = read(updated.encode("utf-8"), suffix=format, schema=schema)
    if parsed is None:
        errors.append(f"Could not read the table as {format.upper()}.")
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
    reset: bool = False,
):
    """Edit ``frame`` and return the edited frame.

    With ``schema``, columns are coerced to its declared dtypes and every row
    is validated; ``errors`` is filled in place.  The schema itself is
    read-only: it never edits columns, it only constrains types and validation.
    """
    data_key = f"{key}-data"
    if reset or data_key not in st.session_state:
        seed = frame
        if schema:
            seed, _ = coerce_frame(frame, schema, errors)
        st.session_state[data_key] = seed

    changes = column_controls(key)
    edited = editable_table(key, column_config=column_config, reset=bool(changes))

    if schema:
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
    reset: bool = False,
) -> pl.DataFrame:
    """Render ``st.data_editor`` for ``st.session_state[f"{key}-data"]``.

    Edits accumulate against a stable base (``{key}-base``) rather than being
    re-fed as the editor input, which would lag by one run.  Pass
    ``reset=True`` when the table is replaced programmatically.
    """
    data_key = f"{key}-data"
    base_key = f"{key}-base"
    revision_key = f"{key}-revision"
    if reset or base_key not in st.session_state:
        st.session_state[base_key] = st.session_state[data_key]
        st.session_state[revision_key] = st.session_state.get(revision_key, 0) + 1
    edited = st.data_editor(
        st.session_state[base_key].to_pandas(),
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key=f"{key}-{st.session_state[revision_key]}",
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
