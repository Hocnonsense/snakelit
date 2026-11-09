"""Store-backed file editors."""

from __future__ import annotations

import streamlit as st

from .filetypes import BINARY_SUFFIXES, IMAGE_SUFFIXES, suffix
from .types import Editors, FileStore


def text_edit(text: str, key: str):
    """Render an editable text area and return its current value.

    The key comes from whoever calls this (the file manager passes the path),
    so multiple editable views never collide.
    """
    return st.text_area("Content", value=text, key=f"{key}-text", height=420)


def edit_for(path: str, store: FileStore, key: str, *, editors: Editors | None = None):
    """Render ``path``'s editor and write the result back to ``store``.

    The editor is chosen by suffix: a host-provided one from ``editors`` when
    available, a plain text area for other text, nothing for images and
    binaries.  A host editor returns the original bytes when the file did not
    change, so nothing is written then.  Missing files start empty, so the
    same call creates them; a successful change writes and reruns.
    """
    content = store.read(path) or b""
    ext = suffix(path)
    if editors and ext in editors:
        edited = editors[ext](path, content, key)
    elif ext in IMAGE_SUFFIXES or ext in BINARY_SUFFIXES:
        return
    else:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return
        edited = text_edit(text=text, key=key).encode("utf-8")
    if edited != content:
        store.write(path, edited)
        st.rerun()
