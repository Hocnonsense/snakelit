"""The raw text editor shared by the mapping and table editors."""

from __future__ import annotations

import streamlit as st


def text_editor(
    text: str,
    key: str,
    *,
    height: int = 420,
    language: str | None = None,
) -> str:
    """Render the raw text editor and return its contents."""
    if language in ("yaml", "json"):
        try:
            from streamlit_ace import st_ace
        except ModuleNotFoundError as error:
            if error.name != "streamlit_ace":
                raise
        else:
            return st_ace(
                text,
                language=language,
                height=height,
                key=f"{key}-ace",
                auto_update=True,
            )
    return st.text_area("Text", value=text, key=f"{key}-editor", height=height)
