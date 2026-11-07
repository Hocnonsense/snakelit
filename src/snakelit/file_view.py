"""A file tree with optional preview and editing.

The model is deliberately tiny: a :class:`File` only needs ``stat`` and an
optional ``preview`` callable.  Directories are inferred from the flat mapping
of paths, and a directory's preview renders its subtree.  No filesystem access
happens here, so the same widget works with the browser deployment, SRPtn, or a
plain in-memory mapping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import streamlit as st

Preview = Callable[[], Any]


@dataclass(frozen=True)
class Stat:
    size: int
    mtime: datetime | None = None


@dataclass
class File:
    stat: Stat
    preview: Preview | None = None


# -- preset previews --------------------------------------------------------


def text_preview(text: str, *, language: str | None = None) -> Preview:
    """Render text as code."""

    def render():
        st.code(text, language=language)

    return render


def image_preview(data: bytes) -> Preview:
    return lambda: st.image(data)


def table_preview(data: bytes, *, format: str = "csv", **read_kwargs) -> Preview:
    def render():
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
                frame = pl.read_csv(buffer, separator="\t", **read_kwargs)
            else:
                frame = pl.read_csv(buffer, **read_kwargs)
        except Exception as error:  # noqa: BLE001 - shown to the user
            st.error(f"Could not read table: {error}")
            return
        st.dataframe(frame, hide_index=True, width="stretch")

    return render


def binary_preview(data: bytes) -> Preview:
    return lambda: st.caption(f"Binary file · {_human_size(len(data))}")


_IMAGE_SUFFIXES = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
_TABLE_SUFFIXES = {"csv", "tsv", "parquet"}
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


def preview_for(path: str, data: bytes) -> Preview | None:
    """Pick a preset for ``data``; undecodable files get a binary caption."""
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in _IMAGE_SUFFIXES:
        return image_preview(data)
    if suffix in _TABLE_SUFFIXES:
        return table_preview(data, format=suffix)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return binary_preview(data)
    return text_preview(text, language=_LANGUAGE_BY_SUFFIX.get(suffix))


# -- tree -------------------------------------------------------------------


def _toggle(state: set[str], path: str):
    if path in state:
        state.remove(path)
    else:
        state.add(path)


def _select(state: dict, path: str):
    if state.get("preview") == path:
        state["preview"] = None
    else:
        state["preview"] = path


def _state(key: str) -> dict:
    state_key = f"{key}-state"
    if state_key not in st.session_state:
        st.session_state[state_key] = {"open": set(), "preview": None}
    return st.session_state[state_key]


def _tree(files: Mapping[str, File]):
    tree: dict = {}
    for path in files:
        node = tree
        parts = path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        node[parts[-1]] = files[path]
    return tree


def _aggregate(node: dict):
    count = 0
    size = 0
    for child in node.values():
        if isinstance(child, dict):
            child_count, child_size = _aggregate(child)
            count += child_count
            size += child_size
        else:
            count += 1
            size += child.stat.size
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


def _render(
    node: dict, files: Mapping[str, File], key: str, state: dict, base="", depth=0
):
    for name in sorted(node):
        namecol, stats = st.columns([3, 1])
        spacer, content = namecol.columns([depth * 0.1 + 0.001, 1])
        child: File = node[name]
        path = f"{base}{name}" if base else name
        if isinstance(child, dict):
            open_ = path in state["open"]
            content.button(
                ("▾ " if open_ else "▸ ") + name,
                key=f"{key}-dir-{path}",
                on_click=_toggle,
                args=(state["open"], path),
            )
            count, size = _aggregate(child)
            stats.caption(f"{count} files, {_human_size(size)}")
            if open_:
                _render(child, files, key, state, path, depth + 1)
        else:
            content.button(
                name,
                key=f"{key}-file-{path}",
                disabled=child.preview is None,
                on_click=_select,
                args=(state, path),
            )
            stats.caption(_human_size(child.stat.size))


def st_container_maxheight(key: str, **kwargs):
    """Set a max-height for a container,
    so tall trees are scrollable while short ones shrink.
    """
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", key)
    height = kwargs.pop("height", 650)
    st.html(f"""<style>
        .st-key-{safe} {{
            max-height: {height}px;
            overflow-y: auto;
        }}
        </style>""")
    return st.container(key=safe, **kwargs)


def file_view(
    files: Mapping[str, File], *, key: str = "snakelit-files", header="Files"
):
    """Render ``files`` as a collapsible tree with a preview panel."""
    st.subheader(header)
    state = _state(key)
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", key)
    with st_container_maxheight(f"{safe}-tree"):
        _render(_tree(files), files, key, state)
    if state["preview"]:
        child = files[state["preview"]]
        if child.preview:
            st.markdown(f"Preview `{state['preview']}`")
            with st_container_maxheight(f"{safe}-preview"):
                child.preview()
