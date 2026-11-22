"""Editable Polars-backed table widgets.

``create_form`` seeds ``st.data_editor`` from the frame it is given; the
editor's widget state carries the edits, and the caller decides where the
returned frame goes.  ``column_controls`` renders icon add/rename/remove/move
popovers that replace the frame before it is edited.  ``schema_table`` adds
optional row-schema coercion and validation on top of a bytes value.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import sys
import polars as pl
import streamlit as st

try:
    from streamlit_sortables import sort_items
except ModuleNotFoundError as error:
    if error.name != "streamlit_sortables":
        raise
    sort_items = None

from .table_schema import coerce_frame, table_errors
from .schema import schema_editor
from ..utils import table

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
    # A file that cannot be read is not an error yet: the text editor takes
    # over below, so this probe keeps its failures to itself.
    frame = table.load(data, suffix=format, errors=[])
    can_text = format in ("csv", "tsv")

    if can_render_form := frame is not None:

        def render_form(problems: list[str]) -> bytes | None:
            edited = create_form(frame, schema, key=key, errors=problems)
            if schema:
                edited, _ = coerce_frame(edited, schema, problems)
            st.session_state[f"{key}-data"] = edited
            if problems or edited.equals(frame):
                return None
            try:
                updated = table.dump(edited, format)
                if updated == data or updated == table.dump(frame, format):
                    return None
            except pl.exceptions.PolarsError as error:
                problems.append(str(error))
                return None
            return updated

    elif not can_text:
        errors.append(f"Cannot edit broken {format.upper()} table as text.")
        return None

    def validate_table(contents: bytes, schema: Mapping | None):
        problems: list[str] = []
        # The initial probe has already parsed these exact bytes on success.
        parsed = frame if contents is data else None
        if parsed is None:
            parsed = table.load(contents, suffix=format, errors=problems)
        if parsed is not None and schema:
            parsed, _ = coerce_frame(parsed, schema, problems)
            problems.extend(table_errors(parsed, schema))
        return problems

    return schema_editor(
        data,
        errors,
        schema,
        header,
        key=key,
        format=format,
        can_text=can_text,
        render_form=render_form if can_render_form else None,
        validate=validate_table,
    )


def create_form(
    frame: pl.DataFrame,
    schema: Mapping | None = None,
    *,
    key: str = "table",
    column_config: Mapping | None = None,
    errors: list[str] | None = None,
):
    """Edit ``frame`` and return the edited frame.

    A supplied schema sets the initial column dtypes. The caller validates
    the resulting frame before saving it.
    """
    data_key = f"{key}-data"
    if schema:
        # input frame is loaded without schema (default strings for csv/tsv),
        # so coerce it to the schema before comparing.
        frame, _ = coerce_frame(frame, schema, errors)

    current: pl.DataFrame | None = st.session_state.get(data_key)
    reset = current is None or not current.equals(frame)
    if reset:
        # The host's frame is the truth: refresh the copy whenever it changed,
        # so an unmounted editor or a document changed elsewhere cannot leave
        # stale rows behind.
        st.session_state[data_key] = frame
    change = column_controls(key)
    return editable_table(
        key,
        column_config=column_config,
        reset=reset or bool(change),
    )


# Shared controls originate in srptn/common/components/table_editor.py.
def column_controls(
    key: str,
    *,
    controls: Mapping[str, Control] | None = None,
    extras: Mapping[str, Control] | None = None,
):
    """Render icon column popovers for ``st.session_state[f"{key}-data"]``.

    Returns the changes applied, keyed by control name (``add``/``rename``/
    ``remove``/``move``, plus any ``extras`` key).  The mapping is empty when
    nothing changed.

    ``controls`` replaces the default controls; ``extras`` renders additional
    controls next to them.  Each follows :data:`Control` and is threaded the
    current ``{key}-data`` frame.
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

    The current data lives in ``{key}-data``; the edited result is written back
    there and returned.  Edits accumulate against a separate stable **base**
    (``{key}-base``) rather than re-feeding ``{key}-data`` as the editor input,
    which would make edits lag by one run.  Pass ``reset=True`` when the table
    is replaced programmatically (column change, upload, fill, clear) so the
    base is re-seeded and the widget rebuilt.

    With ``drop_empty`` (the default) rows whose cells are all blank are
    removed, so empty rows added in the editor are not persisted.
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
    result = _from_pandas(edited)
    result = _drop_empty_rows(result) if drop_empty else result
    st.session_state[data_key] = result
    return result


def _drop_empty_rows(frame: pl.DataFrame):
    """Drop rows where every cell is null or blank."""
    if frame.height == 0 or not frame.columns:
        return frame
    if sys.platform == "emscripten" or any(
        dtype.is_nested() or dtype == pl.Binary for dtype in frame.dtypes
    ):
        return _drop_empty_rows_by_value(frame)
    blank = [
        pl.col(column).is_null()
        | (pl.col(column).cast(pl.Utf8).str.strip_chars() == "")
        for column in frame.columns
    ]
    return frame.filter(~pl.all_horizontal(blank))


def _from_pandas(frame):
    """Rebuild a Polars frame from the data editor's pandas frame.

    Polars' own pandas bridge creates string columns that later panic with
    ``capacity overflow`` when converted back to pandas under Pyodide
    (polars 1.33).  Going through plain Python values avoids that path.
    """
    if sys.platform != "emscripten":
        return pl.from_pandas(frame)

    import pandas as pd

    def cell(value):
        if value is None or value is pd.NA or value is pd.NaT:
            return None
        if isinstance(value, float) and value != value:
            return None
        return value

    data = {
        name: [cell(value) for value in values]
        for name, values in frame.to_dict(orient="list").items()
    }
    overrides: dict[str, type[pl.DataType]] = {}
    for name, dtype in frame.dtypes.items():
        if pd.api.types.is_bool_dtype(dtype):
            overrides[name] = pl.Boolean
        elif pd.api.types.is_unsigned_integer_dtype(dtype):
            overrides[name] = pl.UInt64
        elif pd.api.types.is_integer_dtype(dtype):
            overrides[name] = pl.Int64
        elif pd.api.types.is_float_dtype(dtype):
            overrides[name] = pl.Float64
        elif not pd.api.types.is_object_dtype(dtype) and pd.api.types.is_string_dtype(
            dtype
        ):
            overrides[name] = pl.Utf8
        elif pd.api.types.is_object_dtype(dtype) and not any(
            value is not None for value in data[name]
        ):
            overrides[name] = pl.Utf8
    return pl.DataFrame(data, schema_overrides=overrides)


def _drop_empty_rows_by_value(frame: pl.DataFrame):
    """Drop rows where every cell is null or blank.

    The mask is applied while rebuilding the frame from Python values instead
    of ``frame.filter``: Polars 1.33 under Pyodide corrupts string columns when
    a filtered frame is converted back to pandas (``capacity overflow``).
    """
    if frame.height == 0 or not frame.columns:
        return frame
    keep = [
        any(
            value is not None and (not isinstance(value, str) or value.strip() != "")
            for value in row
        )
        for row in frame.iter_rows()
    ]
    if all(keep):
        return frame
    data = {
        name: [value for value, wanted in zip(frame[name].to_list(), keep) if wanted]
        for name in frame.columns
    }
    return pl.DataFrame(data, schema=frame.schema)


def _native_column_order(key: str, options: list[str]):
    selected = st.selectbox("Move column", options, key=f"{key}-move-column")
    target = st.selectbox("Move before", ["(end)", *options], key=f"{key}-move-target")
    if not st.button("Move", key=f"{key}-move-button") or target == selected:
        return options
    order = [column for column in options if column != selected]
    index = len(order) if target == "(end)" else order.index(target)
    order.insert(index, selected)
    return order


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
            if sort_items is None:
                order = _native_column_order(key, options)
            else:
                # Remount after an external change to the column set or order.
                order = sort_items(
                    options, direction="vertical", key=f"{key}-order-{options!r}"
                )
        else:
            st.caption("Need at least two columns to reorder.")
            order = options
    if list(order) != options and sorted(order) == sorted(options):
        return frame.select(list(order)), order


_default_controls = {
    "add": _add_column,
    "rename": _rename_column,
    "remove": _delete_column,
    "move": _move_column,
}
