"""Plain data types shared by snakelit widgets and their backends."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
