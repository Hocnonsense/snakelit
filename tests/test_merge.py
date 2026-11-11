"""Incoming-file comparison and zip archives."""

import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snakelit.merge import diff_files, file_status  # noqa: E402
from snakelit.types import FileStore, Stat  # noqa: E402
from snakelit.utils.zip import ArchiveError, unzip, zipped  # noqa: E402


class Store(FileStore):
    def __init__(self, files=None):
        self.files = dict(files or {})

    def paths(self):
        return list(self.files)

    def stat(self, path):
        content = self.files.get(path)
        return None if content is None else Stat(len(content))

    def show(self, path, mode="Preview"):
        return None

    def read(self, path):
        return self.files.get(path)

    def write(self, path, data):
        self.files[path] = data

    def rm(self, path):
        self.files.pop(path, None)


def test_unzip_extracts_files_and_skips_metadata():
    store = Store(
        {
            "workflow/Snakefile": b"rule all:\n",
            "__MACOSX/._Snakefile": b"junk",
            ".DS_Store": b"junk",
        }
    )

    assert unzip(zipped(store)) == {"workflow/Snakefile": b"rule all:\n"}


def test_unzip_rejects_an_invalid_archive():
    with pytest.raises(ArchiveError, match="valid zip"):
        unzip(b"not a zip")


def test_zipped_round_trips_a_store():
    store = Store({"a.txt": b"A", "dir/b.bin": b"B"})

    assert unzip(zipped(store)) == {"a.txt": b"A", "dir/b.bin": b"B"}


def test_diff_files_only_keeps_differing_paths():
    store = Store({"a.txt": b"A", "b.txt": b"B"})
    pending = diff_files(
        store,
        {"a.txt": b"A", "b.txt": b"B", "new.txt": b"N", "gone.txt": b"G"},
    )

    assert pending == {"gone.txt": b"G", "new.txt": b"N"}


def test_file_status_distinguishes_local_incoming_and_conflicts():
    assert file_status(b"base", b"base", b"new") == "incoming changed"
    assert file_status(b"base", b"new", b"base") == "local changed"
    assert file_status(b"base", b"local", b"incoming") == "conflict"
    assert file_status(None, None, b"new") == "added in incoming"
    assert file_status(None, b"new", None) == "added locally"
    assert file_status(b"base", None, b"base") == "deleted locally"
    assert file_status(b"base", b"base", None) == "deleted in incoming"
    assert file_status(b"base", b"base", b"base") == "same"
