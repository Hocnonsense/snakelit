"""Human-readable formatting helpers."""

from __future__ import annotations


def human_size(size: int):
    """Format a byte count for display."""
    value = float(size)
    if value < 1024:
        return f"{value} B"
    for unit in ("KB", "MB", "GB"):
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value} GB"
