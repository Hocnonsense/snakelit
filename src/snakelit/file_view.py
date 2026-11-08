"""A file tree backed by a :class:`FileStore`.

The store supplies the paths, stats and preview callables; the widget only
arranges them as a collapsible tree.  No filesystem access happens here, so
the same widget works with the browser deployment, SRPtn, or a plain in-memory
store.
"""

from __future__ import annotations

import re
from functools import partial
from pathlib import Path

import streamlit as st

from .types import FileStore
from .utils.st_layouts import st_container_maxheight
from .utils.ui_components import toggle_button

# -- preset previews --------------------------------------------------------


def text_view(text: str, *, language: str | None = None):
    """Render text."""
    st.code(text, language=language)


def text_edit(text: str, key: str):
    """Render an editable text area and return its current value.

    The key comes from whoever calls this (the file manager passes the path),
    so multiple editable views never collide.
    """
    return st.text_area("Content", value=text, key=f"{key}-text", height=420)


def image_view(data: bytes):
    st.image(data)


def table_view(data: bytes, *, format: str = "csv", **read_kwargs):
    import io

    try:
        import polars as pl
    except ImportError:
        st.error("polars is not installed; cannot preview tables.")
        return
    try:
        buffer = io.BytesIO(data)
        if format == "parquet":
            frame = pl.read_parquet(buffer, **read_kwargs)
        elif format == "tsv":
            frame = pl.read_csv(buffer, separator="	", **read_kwargs)
        else:
            frame = pl.read_csv(buffer, **read_kwargs)
    except Exception as error:  # noqa: BLE001 - shown to the user
        st.error(f"Could not read table: {error}")
        return
    st.dataframe(frame, hide_index=True, width="stretch")


def binary_view(data: bytes):
    st.caption(f"Binary file · {_human_size(len(data))}")


_IMAGE_SUFFIXES = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
_TABLE_SUFFIXES = {"csv", "tsv", "parquet"}
_BINARY_SUFFIXES = {"bin", "dat", "exe", "dll", "so", "o", "a", "class"}
_LANGUAGE_BY_SUFFIX = {
    "yaml": "yaml",
    "yml": "yaml",
    "json": "json",
    "py": "python",
    "smk": "python",
    "md": "markdown",
    "sh": "bash",
    "toml": "toml",
    "csv": "csv",
    "tsv": "tsv",
}


def preview_for(path: str, data: bytes):
    """Render ``data`` with the preset that matches its suffix."""
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in _IMAGE_SUFFIXES:
        return image_view(data)
    if suffix in _TABLE_SUFFIXES:
        return table_view(data, format=suffix)
    if suffix in _BINARY_SUFFIXES:
        return binary_view(data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return binary_view(data)
    return text_view(text, language=_LANGUAGE_BY_SUFFIX.get(suffix))


def edit_for(path: str, data: bytes, key: str, *, editors=None):
    """Render an editor for ``data`` and return the current bytes.

    Returns ``None`` when the file is not text (images, tables, binaries or
    undecodable content), so the caller can fall back to a preview.  YAML
    mappings use :func:`snakelit.editors.schema_dict`; unchanged or invalid
    input yields the original bytes so the caller writes nothing.
    """
    suffix = Path(path).suffix.lower().lstrip(".")
    if editors and suffix in editors:
        return editors[suffix](path, data, key)
    if suffix in _IMAGE_SUFFIXES:
        return
    if suffix in _TABLE_SUFFIXES:
        return
    if suffix in _BINARY_SUFFIXES:
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return
    return text_edit(text=text, key=key).encode("utf-8")


# -- tree -------------------------------------------------------------------


def _toggle(state: set[str], path: str):
    if path in state:
        state.remove(path)
    else:
        state.add(path)


def _select(state: dict, path: str):
    preview = state.get("preview")
    if preview and preview[0] == path:
        state["preview"] = None
    else:
        state["preview"] = path, ()


def change_preview(key: str, path: str, args=()):
    """Select ``path`` in the explorer rendered with ``key``."""
    _state(key)["preview"] = path, args


def _state(key: str) -> dict:
    state_key = f"{key}-state"
    if state_key not in st.session_state:
        st.session_state[state_key] = {"open": set(), "preview": None}
    return st.session_state[state_key]


def _aggregate(store: FileStore, node: dict):
    count = 0
    size = 0
    for child in node.values():
        if isinstance(child, dict):
            child_count, child_size = _aggregate(store, child)
            count += child_count
            size += child_size
        else:
            count += 1
            stat = store.stat(child)
            if stat is not None:
                size += stat.size
    return count, size


def _human_size(size: int):
    value = float(size)
    if value < 1024:
        return f"{value} B"
    for unit in ("KB", "MB", "GB"):
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value} GB"


def natural_key(s: str):
    def seg(t: str):
        if t.isdecimal():
            return 1, int(t)
        return 0 if t.startswith(".") else 2, t.lower()

    return (
        not s.startswith("."),
        *((seg(t), t) for t in re.split(r"(\d+)", s) if t),
    )


def _render(store: FileStore, node: dict, key: str, state: dict, base="", depth=0):
    for name in sorted(node, key=natural_key):
        namecol, stats = st.columns([3, 1])
        spacer, content = namecol.columns([depth * 0.1 + 0.001, 1])
        child = node[name]
        dir_path = f"{base}{name}" if base else name
        if isinstance(child, dict):
            open_ = dir_path in state["open"]
            content.button(
                ("▾ " if open_ else "▸ ") + name,
                key=f"{key}-dir-{dir_path}",
                on_click=_toggle,
                args=(state["open"], dir_path),
            )
            count, size = _aggregate(store, child)
            stats.caption(f"{count} files, {_human_size(size)}")
            if open_:
                _render(store, child, key, state, dir_path, depth + 1)
        else:
            path = child
            content.button(
                name,
                key=f"{key}-file-{path}",
                disabled=store.show(path) is None,
                on_click=_select,
                args=(state, path),
            )
            stat = store.stat(path)
            stats.caption(_human_size(stat.size) if stat is not None else "")


def file_view(state: dict, store: FileStore, key: str, *, editors=None):
    if not state["preview"]:
        return
    path, args = state["preview"]
    mode = "Edit" if "edit" in args else "Preview"
    exists = store.stat(path) is not None

    head, delete, edit = st.columns([3, 1, 1])
    if mode == "Edit":
        head.markdown(f"Edit `{path}`" if exists else f"New file `{path}`")
        if exists:
            if edit.button("Preview", key=f"{key}-preview-toggle", width="stretch"):
                state["preview"] = (path, ())
                st.rerun()
            if delete.button("Delete", key=f"{key}-delete", width="stretch"):
                store.rm(path)
                state["preview"] = None
                st.rerun()
        elif delete.button("Cancel", key=f"{key}-cancel", width="stretch"):
            state["preview"] = None
            st.rerun()
    else:
        head.markdown(f"Preview `{path}`")
        if edit.button(
            "Edit" if exists else "Create", key=f"{key}-edit-toggle", width="stretch"
        ):
            state["preview"] = (path, ("edit",))
            st.rerun()
        if delete.button("hide", key=f"{key}-hide", width="stretch"):
            state["preview"] = None
            st.rerun()

    with st_container_maxheight(f"{key}-preview"):
        preview = store.show(path, mode)
        if preview is not None:
            preview()


def file_explorer(
    store: FileStore,
    *,
    key: str = "snakelit-files",
    header="Files",
    editors=None,
):
    """Render ``store`` as a collapsible tree with a preview panel.

    Returns ``change_preview(path, args)``; the host can select a file and
    pass args that its preview understands (for example an editing mode).
    """
    state = _state(key)
    if toggle_button(header, key=f"{key}-header"):
        with st_container_maxheight(f"{key}-tree"):
            _render(store, store.tree(), key, state)
    file_view(state, store, key, editors=editors)

    return partial(change_preview, key)
