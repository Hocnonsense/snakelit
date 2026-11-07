"""Small Streamlit layout helpers."""

from __future__ import annotations

import re

import streamlit as st


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
