"""Compare an incoming file set with a :class:`FileStore`.

The merge view is deliberately store-agnostic: it reads and writes through
the :class:`FileStore` protocol, and the caller supplies the baseline bytes
(used only to describe what changed) and the cancel action.
"""

from __future__ import annotations

from typing import Callable, Mapping

import streamlit as st

from .filetypes import BINARY_SUFFIXES, IMAGE_SUFFIXES, suffix
from .preview import binary_view, image_view
from .types import FileStore


def diff_files(store: FileStore, incoming: Mapping[str, bytes]):
    """Map every differing path to its incoming bytes (``None`` = deleted)."""
    return {
        path: incoming.get(path)
        for path in sorted(set(store.paths()) | set(incoming))
        if store.read(path) != incoming.get(path)
    }


def file_status(base: bytes | None, local: bytes | None, incoming: bytes | None):
    """Describe how ``local`` and ``incoming`` differ from their common ``base``."""
    if local == incoming:
        return "same"
    if local == base:
        if incoming is None:
            return "deleted in incoming"
        if base is None:
            return "added in incoming"
        return "incoming changed"
    if incoming == base:
        if local is None:
            return "deleted locally"
        if base is None:
            return "added locally"
        return "local changed"
    if local is None:
        return "deleted locally, incoming changed"
    if incoming is None:
        return "deleted in incoming, local changed"
    return "conflict"


def render_merge(
    store: FileStore,
    header: str,
    files: dict[str, bytes | None],
    *,
    base: Mapping[str, bytes] | None,
    on_cancel: Callable[[], None],
    key: str = "merge",
):
    """Render the per-file incoming/local comparison.

    ``header`` is the already-formatted title (for example
    ``"Merge me/wf@main (abc1234)"``).  ``files`` is the dict returned by
    :func:`diff_files`; resolving a row pops its key.  An empty dict means the
    merge is complete.  ``base`` maps paths to the bytes both sides started
    from, which is only used for the status text.  ``on_cancel`` clears the
    caller's merge state before the rerun.
    """
    if not files:
        return

    title, cancel = st.columns([4, 1], vertical_alignment="bottom")
    title.subheader(header)
    if cancel.button("Cancel comparison", key=f"{key}-discard", width="stretch"):
        on_cancel()
        st.rerun()
    for path in sorted(files):
        empty = st.empty()
        if render_file(store, path, files[path], empty.container(), base=base, key=key):
            files.pop(path, None)
            empty.empty()
            if not files:
                st.rerun()


def render_file(
    store: FileStore,
    path: str,
    remote: bytes | None,
    container=None,
    *,
    base: Mapping[str, bytes] | None = None,
    key: str = "merge",
):
    if container is None:
        container = st
    local = store.read(path)
    original = (base or {}).get(path)
    status = file_status(original, local, remote)
    apply_col, name_col, delete_col, finish_col = container.columns(
        [1, 4, 1, 1], vertical_alignment="center"
    )
    if apply_col.button(
        "Apply",
        key=f"{key}-apply-{path}",
        width="stretch",
        help="Accept incoming (theirs)",
    ):
        if remote is None:
            store.rm(path)
        else:
            store.write(path, remote)
        return True
    name_col.markdown(f"**`{path}`** · {status}")
    if local is not None and delete_col.button(
        "Delete",
        key=f"{key}-delete-{path}",
        width="stretch",
        help="Delete the local file and finish",
    ):
        store.rm(path)
        return True
    if finish_col.button(
        "Finish",
        key=f"{key}-finish-{path}",
        width="stretch",
        help="Accept current (ours)",
    ):
        return True

    left, right = container.columns(2)
    widget_key = f"{key}-local-{path}"

    def save():
        value = st.session_state.get(widget_key)
        if value is not None:
            store.write(path, value.encode("utf-8"))

    with left:
        _show_bytes(remote, path, widget_key, None)
    with right:
        _show_bytes(local, path, widget_key, save)


def _show_bytes(data: bytes | None, path: str, key: str, save, height=420):
    if data is None:
        st.caption("(not present)")
        return
    ext = suffix(path)
    if ext in IMAGE_SUFFIXES:
        return image_view(data)
    if ext in BINARY_SUFFIXES:
        return binary_view(data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return binary_view(data)

    label = "Incoming" if save is None else "Local"
    st.text_area(
        label,
        value=text,
        key=f"{key}-preview" if save is None else key,
        height=height,
        on_change=save,
        disabled=save is None,
        label_visibility="collapsed",
    )
