"""SRPtn-style ref row and full-width list, with time in parentheses."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snakelit.version_picker import Ref  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

SCRIPT = """
from datetime import datetime, timezone

import streamlit as st
from snakelit.version_picker import Ref, version_picker

D1 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
D2 = datetime(2026, 11, 2, 11, 30, tzinfo=timezone.utc)

TAGS = [
    Ref("tag", "v1", "a" * 12, time=D1, subject="first"),
    Ref("tag", "v2", "b" * 12, time=D2, subject="second"),
]
BRANCHES = [
    Ref("branch", "main", "c" * 12, time=D1, subject="main"),
    Ref("branch", "dev", "c" * 12, time=D2, subject="dev"),
]
COMMITS = [Ref("commit", "d" * 12, "d" * 12, time=D1, subject="subject")]


def load(kind):
    if kind == "tag":
        return iter(TAGS)
    if kind == "branch":
        return iter(BRANCHES)
    return iter(COMMITS)


ref = version_picker("v1", load)
st.write(f"{ref.kind}:{ref.name}" if ref else "none")
"""


def _button(at, key):
    return next(item for item in at.button if item.key == key)


def _labels(at):
    return [item.label for item in at.button]


def _text(at):
    return "\n".join(item.value for item in at.markdown)


def _app():
    at = AppTest.from_string(SCRIPT, default_timeout=60)
    at.run()
    return at


def test_initial_row_shows_values_and_time():
    at = _app()

    assert not at.exception
    labels = _labels(at)
    assert any(
        "v1 (2026-11-01 10:00 UTC)" in label and label.endswith("▾") for label in labels
    )
    assert "tag:v1" in _text(at)


def test_tag_picker_selects():
    at = _app()
    _button(at, "snakelit-refs-kind-tag").click()
    at.run()

    radio = at.radio[0]
    radio.set_value(radio.options[1])
    at.run()

    assert any("v2 (2026-11-02 11:30 UTC)" in label for label in _labels(at))
    assert "tag:v2" in _text(at)


def test_branch_picker_selects():
    at = _app()
    _button(at, "snakelit-refs-kind-branch").click()
    at.run()
    radio = at.radio[0]
    radio.set_value(radio.options[1])
    at.run()

    assert any("dev (2026-11-02 11:30 UTC)" in label for label in _labels(at))
    assert "branch:dev" in _text(at)


def test_commit_picker_selects():
    at = _app()
    _button(at, "snakelit-refs-kind-commit").click()
    at.run()
    radio = at.radio[0]
    radio.set_value(radio.options[0])
    at.run()

    assert "commit:" + "d" * 12 in _text(at)


def test_item_label_contains_time_and_subject():
    ref = Ref(
        "tag",
        "v1",
        "a" * 12,
        time=datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc),
        subject="first",
    )
    assert "(2026-11-01 10:00 UTC)" in ref.value_subject
    assert "first" in ref.value_subject


PAGED_SCRIPT = SCRIPT.replace(
    'TAGS = [\n    Ref("tag", "v1", "a" * 12, time=D1, subject="first"),\n    Ref("tag", "v2", "b" * 12, time=D2, subject="second"),\n]',
    'TAGS = [Ref("tag", f"v{i}", f"{i:012d}", time=D1, subject="tag") for i in range(1, 46)]',
)


def test_prev_next_paginate_the_list():
    at = AppTest.from_string(PAGED_SCRIPT, default_timeout=60)
    at.run()
    _button(at, "snakelit-refs-kind-tag").click()
    at.run()

    assert len(at.radio[0].options) == 20
    assert at.radio[0].options[0].startswith("v1 (")

    _button(at, "snakelit-refs-next").click()
    at.run()
    assert at.radio[0].options[0].startswith("v21 (")

    _button(at, "snakelit-refs-prev").click()
    at.run()
    assert at.radio[0].options[0].startswith("v1 (")
