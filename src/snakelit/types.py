"""Plain data types shared by snakelit widgets and their backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

Renderer = Callable[[], None]
"""What ``FileStore.show`` returns: renders a file into the page."""

Editor = Callable[[str, bytes, str], bytes]
"""A host editor: ``(path, data, key)`` -> the new bytes (unchanged -> ``data``)."""

Editors = Mapping[str, Editor]
"""Host editors keyed by file suffix."""


@dataclass(frozen=True)
class Stat:
    """What the file tree needs to know about a file."""

    size: int
    mtime: datetime | None = None


class FileStore(ABC):
    """A collection of POSIX, repo-relative file paths.

    Bytes rather than text: tables and other binaries never have to pass
    through a lossy ``str`` step.  ``show`` returns the renderer for a file,
    or ``None`` when it cannot be shown.
    """

    @abstractmethod
    def paths(self, dir="") -> Iterable[str]:
        """Return every file path in the store (POSIX, repo-relative)."""

    def tree(self):
        """Nested view of :meth:`paths` for the file manager.

        Directories are the dicts; leaves are the path strings themselves.
        Hosts can override this when they can build the tree more cheaply.
        """
        tree: dict[str, Any] = {}
        for path in self.paths():
            parts = path.split("/")
            node = tree
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = path
        return tree

    @abstractmethod
    def stat(self, path: str) -> Stat | None:
        """Return the file's size and mtime, or ``None`` if it is missing."""

    @abstractmethod
    def show(self, path: str, mode="Preview") -> Renderer | None:
        """Return the renderer for ``path``, or ``None`` if not showable."""

    @abstractmethod
    def read(self, path: str) -> bytes | None:
        """Return the content of ``path``, or ``None`` if it is missing."""

    @abstractmethod
    def write(self, path: str, data: bytes) -> None:
        """Write ``data`` to ``path``, creating parents as needed."""

    @abstractmethod
    def rm(self, path: str) -> None:
        """Remove the file at ``path``."""


@dataclass(frozen=True)
class Ref:
    kind: str
    name: str
    """the stable identifier within a kind: tag/branch name, or the commit sha.
    Widget keys are derived from it, so it must be unique."""
    sha: str
    time: datetime | None = None
    """optional display metadata supplied by the host (committer date)."""
    subject: str | None = None
    """optional (first line of the message)."""

    KINDS = "tag", "branch", "commit"

    def _value(self):
        return self.sha[:7] if self.kind == "commit" and self.sha else self.name

    @property
    def value_time(self):
        return self._value() + _time(self.time)

    @property
    def value_subject(self):
        value = self.value_time
        if self.subject:
            value += f" · {self.subject}"
        return value


def _time(value: datetime | None):
    return f" ({value:%Y-%m-%d %H:%M} UTC)" if value else ""
