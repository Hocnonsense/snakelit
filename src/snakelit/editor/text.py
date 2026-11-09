"""The raw text editor shared by the mapping and table editors."""

from __future__ import annotations

from typing import Any, Mapping

import streamlit as st

from ..utils.schema import is_schema
from ..utils.yaml import dump as dump_yaml


def schema_text_editor(
    text: str,
    schema: Mapping[str, Any] | None,
    key: str,
    *,
    height: int = 420,
):
    """Render the raw text editor, with the schema beside it when given."""
    editor = st
    if is_schema(schema):
        editor, viewer = st.columns([2, 1])
        viewer.code(dump_yaml(schema), "yaml", height=height)
    return editor.text_area("Text", value=text, key=f"{key}-editor", height=height)
