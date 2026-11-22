"""Incoming-file comparison and zip archives."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snakelit.merge import diff_files, file_status  # noqa: E402
from snakelit.utils import zip as archive  # noqa: E402


class Store:
    def __init__(self, files=None):
        self.files = dict(files or {})

    def paths(self, dir=""):
        return list(self.files)

    def read(self, path):
        return self.files.get(path)

    def write(self, path, data):
        self.files[path] = data

    def rm(self, path):
        self.files.pop(path, None)


def test_unzip_extracts_files_and_skips_metadata():
    files = {
        "workflow/Snakefile": b"rule all:\n",
        "__MACOSX/._Snakefile": b"junk",
        ".DS_Store": b"junk",
    }
    assert archive.load(archive.dump(files)) == {"workflow/Snakefile": b"rule all:\n"}


def test_unzip_rejects_an_invalid_archive():
    with pytest.raises(archive.ArchiveError, match="valid zip"):
        archive.load(b"not a zip")


def test_zip_round_trips_a_file_mapping():
    files = {"a.txt": b"A", "dir/b.bin": b"\x00\xff", "empty.txt": b""}
    assert archive.load(archive.dump(files)) == files


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
