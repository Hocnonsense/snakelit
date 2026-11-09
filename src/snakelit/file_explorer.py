"""A file tree backed by a :class:`FileStore`.

The store supplies the paths, stats and preview callables; the widget only
arranges them as a collapsible tree.  No filesystem access happens here, so
the same widget works with the browser deployment, SRPtn, or a plain in-memory
store.
"""

from __future__ import annotations

import re

import streamlit as st

from .types import FileStore
from .utils.format import human_size
from .utils.st_layouts import st_container_maxheight
from .utils.ui_components import toggle_button


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
                stats.caption(f"{count} files, {human_size(size)}")
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
                stats.caption(human_size(stat.size) if stat is not None else "")

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
        preview = self.store.show(path, mode)
        if preview is None:
            return
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
            preview()
