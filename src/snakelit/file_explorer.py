"""A file tree backed by a :class:`FileStore`.

The store supplies the paths, stats and preview callables; the widget only
arranges them as a collapsible tree.  No filesystem access happens here, so
the same widget works with the browser deployment, SRPtn, or a plain in-memory
store.
"""

from __future__ import annotations

import re
from typing import Callable

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


def _valid_path(target: str, tree: Callable[[], dict]):
    """Normalise ``target`` and resolve it in the store tree.

    Returns ``(formatted, node)``.  ``formatted`` is ``None`` for paths
    containing ``..``; ``node`` is the directory (dict) or file (str) the
    target points at, and ``None`` when it does not exist.
    """
    parts = [part for part in target.split("/") if part and part != "."]
    if ".." in parts:
        return None, None
    node = tree()
    for part in parts:
        if not isinstance(node, dict):
            return None, None
        node = node.get(part)
        if node is None:
            return "/".join(parts), None
    return "/".join(parts), node


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
            dir_path = f"{base}/{name}" if base else name
            if isinstance(child, dict):
                open_ = dir_path in self.expand_dirs
                content.button(
                    ("▾ " if open_ else "▸ ") + name + "/",
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
        """Render the tree, the upload form and the preview panel."""
        head, upload = st.columns([5, 1], vertical_alignment="bottom")
        with head:
            open_ = toggle_button(header, key=f"{self.key}-header")
        with upload:
            self.upload()
        if open_:
            with st_container_maxheight(f"{self.key}-tree"):
                self._render(self.store.tree())
        self.preview_panel()

    def upload(self):
        """Render the upload form; uploaded files are written to the store."""
        with st.popover("Upload", icon=":material/upload:"):
            target = st.text_input(
                "Target path",
                key=f"{self.key}-upload-path",
                placeholder="folder/ or folder/name.txt",
                help=(
                    "Several files go into this folder. For one file, a trailing "
                    "/ means folder; otherwise the path is its name. A leading / "
                    "is ignored."
                ),
            )
            files = st.file_uploader(
                "Files",
                accept_multiple_files=True,
                key=f"{self.key}-upload-files",
            )
            if not files:
                st.warning("Choose at least one file.")
                return
            folder, sub_tree = _valid_path(target, self.store.tree)
            if folder is None:
                st.error(f"Invalid target path: {target!r}")
                return

            if not isinstance(sub_tree, dict) and (
                len(files) > 1 or target.strip().endswith("/")
            ):
                if sub_tree:
                    st.error(f"{target!r} is a file; choose a folder path.")
                    return
                st.warning(f"Will create folder {folder}/")
                sub_tree = {}
            skipped: set[str] = set()
            if isinstance(sub_tree, dict):
                prefix = f"{folder}/" if folder else ""
                destinations: list[str] = []
                overwritten: list[str] = []
                for file in files:
                    path, subsub_tree = _valid_path(file.name, lambda: sub_tree)
                    if not path or isinstance(subsub_tree, dict):
                        skipped.add(file.name)
                    elif subsub_tree:
                        overwritten.append(f"{prefix}{file.name}")
                    destinations.append(f"{prefix}{file.name}")
                if overwritten:
                    st.warning(
                        "These files will be overwritten: " + ", ".join(overwritten)
                    )
                if skipped:
                    st.warning(
                        "Skipped (invalid path or conflict to an existing directory): "
                        + ", ".join(sorted(skipped))
                    )
            else:
                destinations = [folder]
                if sub_tree:
                    st.warning(f"This file will be overwritten: {folder}")

            if not st.button(
                "Upload", key=f"{self.key}-upload-button", width="stretch"
            ):
                return
            for destination, file in zip(destinations, files):
                if file.name not in skipped:
                    self.store.write(destination, file.getvalue())
            self._expand_to(folder)
            st.rerun()

    def _expand_to(self, path: str):
        """Open the folders leading to ``path``."""
        parts = path.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            self.expand_dirs.add("/".join(parts[:index]))

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
