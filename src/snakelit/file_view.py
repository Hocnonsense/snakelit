"""A file tree backed by a :class:`FileStore`.

The store supplies the paths, stats and preview callables; the widget only
arranges them as a collapsible tree.  No filesystem access happens here, so
the same widget works with the browser deployment, SRPtn, or a plain in-memory
store.
"""

from __future__ import annotations

import re
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


class FileExplorer:
    """File tree and preview state for one :class:`FileStore`."""

    def __init__(self, key: str, store: FileStore):
        self.key = key
        self.store = store
        self.expand_dirs: set[str] = set()
        self.preview: tuple[str, tuple] | None = None

    def toggle(self, path: str):
        """Open or close the directory at ``path``."""
        if path in self.expand_dirs:
            self.expand_dirs.remove(path)
        else:
            self.expand_dirs.add(path)

    def select(self, path: str):
        """Toggle the preview of ``path``."""
        if self.preview and self.preview[0] == path:
            self.preview = None
        else:
            self.preview = path, ()

    def change_preview(self, path: str, args=()):
        """Select ``path`` with the arguments its preview understands."""
        self.preview = path, args

    def aggregate(self, node: dict):
        """Count and total size of the files under ``node``."""
        count = 0
        size = 0
        for child in node.values():
            if isinstance(child, dict):
                child_count, child_size = self.aggregate(child)
                count += child_count
                size += child_size
            else:
                count += 1
                stat = self.store.stat(child)
                if stat is not None:
                    size += stat.size
        return count, size

    def _render(self, node: dict, base="", depth=0):
        store = self.store
        key = self.key
        for name in sorted(node, key=natural_key):
            namecol, stats = st.columns([3, 1])
            spacer, content = namecol.columns([depth * 0.1 + 0.001, 1])
            child = node[name]
            dir_path = f"{base}{name}" if base else name
            if isinstance(child, dict):
                open_ = dir_path in self.expand_dirs
                content.button(
                    ("▾ " if open_ else "▸ ") + name,
                    key=f"{key}-dir-{dir_path}",
                    on_click=self.toggle,
                    args=(dir_path,),
                )
                count, size = self.aggregate(child)
                stats.caption(f"{count} files, {_human_size(size)}")
                if open_:
                    self._render(child, dir_path, depth + 1)
            else:
                path = child
                content.button(
                    name,
                    key=f"{key}-file-{path}",
                    disabled=store.show(path) is None,
                    on_click=self.select,
                    args=(path,),
                )
                stat = store.stat(path)
                stats.caption(_human_size(stat.size) if stat is not None else "")

    def render(self, *, header="Files"):
        """Render the tree and the preview panel."""
        if toggle_button(header, key=f"{self.key}-header"):
            with st_container_maxheight(f"{self.key}-tree"):
                self._render(self.store.tree())
        self.preview_panel()

    def preview_panel(self):
        if not self.preview:
            return
        path, args = self.preview
        mode = "Edit" if "edit" in args else "Preview"
        exists = self.store.stat(path) is not None

        head, delete, edit = st.columns([3, 1, 1])
        if mode == "Edit":
            head.markdown(f"Edit `{path}`" if exists else f"New file `{path}`")
            if exists:
                if edit.button(
                    "Preview", key=f"{self.key}-preview-toggle", width="stretch"
                ):
                    self.preview = (path, ())
                    st.rerun()
                if delete.button("Delete", key=f"{self.key}-delete", width="stretch"):
                    self.store.rm(path)
                    self.preview = None
                    st.rerun()
            elif delete.button("Cancel", key=f"{self.key}-cancel", width="stretch"):
                self.preview = None
                st.rerun()
        else:
            head.markdown(f"Preview `{path}`")
            if edit.button(
                "Edit" if exists else "Create",
                key=f"{self.key}-edit-toggle",
                width="stretch",
            ):
                self.preview = (path, ("edit",))
                st.rerun()
            if delete.button("hide", key=f"{self.key}-hide", width="stretch"):
                self.preview = None
                st.rerun()

        with st_container_maxheight(f"{self.key}-preview"):
            preview = self.store.show(path, mode)
            if preview is not None:
                preview()
