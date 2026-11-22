"""Convert between ZIP bytes and a mapping of file paths to contents.

``load`` reads an uploaded archive into ``path -> bytes`` while rejecting
paths that escape the store.  ``dump`` writes every supplied file
into a new archive, so the two functions round-trip.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping
from pathlib import PurePosixPath

IGNORED_PATTERNS = [".DS_Store", "__MACOSX", "__pycache__"]


class ArchiveError(Exception):
    """The archive cannot be read or contains no usable files."""


def load(data: bytes):
    """Read a zip archive into ``path -> bytes``, rejecting unsafe paths."""
    files: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                path = _zip_path(info.filename)
                if path:
                    files[path] = archive.read(info)
    except zipfile.BadZipFile as error:
        raise ArchiveError("The uploaded file is not a valid zip archive.") from error
    if not files:
        raise ArchiveError("The zip archive contains no files.")
    return files


def dump(files: Mapping[str, bytes]):
    """Serialize relative file paths and their contents to ZIP bytes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.writestr(path, files[path])
    return buffer.getvalue()


def _zip_path(name: str):
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return
    parts = [part for part in path.parts if part not in ("", ".")]
    for pattern in IGNORED_PATTERNS:
        if any(part == pattern for part in parts):
            return
    return "/".join(parts)
