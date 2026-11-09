"""Suffix-dispatched renderers for file content."""

from __future__ import annotations

import streamlit as st

from .filetypes import (
    BINARY_SUFFIXES,
    IMAGE_SUFFIXES,
    LANGUAGE_BY_SUFFIX,
    TABLE_SUFFIXES,
    suffix,
)
from .utils.format import human_size
from .utils.table import read as read_table


def text_view(text: str, *, language: str | None = None):
    """Render text."""
    st.code(text, language=language)


def image_view(data: bytes):
    st.image(data)


def table_view(data: bytes, *, format: str = "csv", **read_kwargs):
    try:
        frame = read_table(data, suffix=format, **read_kwargs)
    except ImportError:
        st.error("polars is not installed; cannot preview tables.")
        return
    st.dataframe(frame, hide_index=True, width="stretch")


def binary_view(data: bytes):
    st.caption(f"Binary file · {human_size(len(data))}")


def preview_for(path: str, data: bytes):
    """Render ``data`` with the preset that matches its suffix."""
    ext = suffix(path)
    if ext in IMAGE_SUFFIXES:
        return image_view(data)
    if ext in TABLE_SUFFIXES:
        return table_view(data, format=ext)
    if ext in BINARY_SUFFIXES:
        return binary_view(data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return binary_view(data)
    return text_view(text, language=LANGUAGE_BY_SUFFIX.get(ext))
