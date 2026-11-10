"""Selection of a workflow ref and the commit it points to.

The host passes:

- ``init_ref``: the tag/branch name or commit sha to preselect;
- ``load(kind)``: return an iterable of :class:`Ref` for ``tag``, ``branch`` or
  ``commit``.

The version row follows SRPtn: three buttons (tag / branch / commit) showing the
current value.  The open kind is rendered as a list of full-width buttons, one
per row, with ``Prev`` / ``Next`` for pagination.  Resolving ``init_ref``
consumes the matching iterable up to that ref.
"""

from __future__ import annotations

from typing import Callable, Iterable, Self

import streamlit as st

from .types import Ref

LoadRefs = Callable[[str], Iterable[Ref]]


class _LazyRefs:
    ROWS_PER_PAGE = 20

    def __init__(self, load: Iterable[Ref]):
        self._load = iter(load)
        self._loaded: list[Ref] = []
        self.page = 0
        self._done = False

    def __iter__(self):
        yield from self._loaded
        for ref in self._load:
            self._loaded.append(ref)
            yield ref
        self._done = True

    def _fill(self, end: int):
        if self._done:
            return
        while len(self._loaded) < end:
            try:
                self._loaded.append(next(self._load))
            except StopIteration:
                self._done = True
                break

    def select(self):
        start = self.page * self.ROWS_PER_PAGE
        end = start + self.ROWS_PER_PAGE
        self._fill(end + 1)
        chunk = self._loaded[start:end]
        return chunk, len(self._loaded) > end

    def try_select(self):
        try:
            self.select()
        except Exception as error:  # noqa: BLE001 - shown by the caller
            return str(error)

    def prev_page(self):
        self.page -= 1
        return self.try_select()

    def next_page(self):
        self.page += 1
        return self.try_select()

    def page_str(self):
        desc = f"Page {self.page + 1}"
        if self._done:
            desc += f"/{len(self._loaded) // self.ROWS_PER_PAGE + 1}"
            desc += f" ({len(self._loaded)} total)"
        return desc


class _State:
    def __init__(self, load: LoadRefs, init_ref: str | None):
        self.load = load
        self.refresh(init_ref)
        self.open = False

    def refresh(self, *init: str | None):
        self.items = {kind: _LazyRefs(self.load(kind)) for kind in Ref.KINDS}
        self.current = self._resolve(init[0] if init else self.current.name)
        self.kind = self.current.kind
        self.error: str | None = None

    def _resolve(self, init_ref: str | None):
        for kind in Ref.KINDS:
            for ref in self.items[kind]:
                if not init_ref or ref.name == init_ref or ref.sha == init_ref:
                    return ref
        raise ValueError("Could not find a valid ref.")

    @classmethod
    def get(cls, key: str, load: LoadRefs, init_ref: str | None) -> Self:
        state_key = f"{key}-state"
        if state_key not in st.session_state:
            st.session_state[state_key] = cls(load, init_ref)
        return st.session_state[state_key]

    def set_kind(self, kind: str):
        self.open = not self.open if kind == self.kind else True
        self.kind = kind
        self.error = self.items[kind].try_select()

    def prev_page(self):
        self.error = self.items[self.kind].prev_page()

    def next_page(self):
        self.error = self.items[self.kind].next_page()

    def choose(self, ref: Ref):
        self.current = ref
        self.open = False

    def current_refs(self):
        current = self.current
        if current.kind == "tag":
            return current, None, None
        elif current.kind == "branch":
            return None, current, None
        elif current.kind == "commit":
            return None, None, current
        raise ValueError(f"Invalid ref kind: {current.kind}")


def _current_refs(state: _State):
    current = state.current
    tag = current if current.kind == "tag" else None
    branch = current if current.kind == "branch" else None
    commit = (
        Ref("commit", current.sha, current.sha, current.time, current.subject)
        if current.sha
        else None
    )
    return tag, branch, commit


def _pick(state: _State, choices: dict[str, Ref], picker_key: str) -> None:
    ref = choices.get(st.session_state.get(picker_key) or "")
    if ref is not None:
        state.choose(ref)


def version_picker(init_ref: str | None, load: LoadRefs, *, key: str = "snakelit-refs"):
    """Render the ref selector and return the chosen ``Ref`` (or ``None``)."""
    try:
        state = _State.get(key, load, init_ref)
    except Exception as error:  # noqa: BLE001 - shown to the user
        st.error(f"Could not load refs: {error}")
        return None
    tag, branch, commit = _current_refs(state)
    widths = [4 if tag else 0.6, 4 if branch else 0.6, 6, 1]
    columns = st.columns(widths, vertical_alignment="center")
    for column, kind, ref in zip(columns, Ref.KINDS, (tag, branch, commit)):
        column.button(
            f"{ref.value_time} ▾" if ref else "▾",
            key=f"{key}-kind-{kind}",
            help=kind.capitalize(),
            width="stretch",
            on_click=state.set_kind,
            args=(kind,),
        )
    columns[3].button("↻", key=f"{key}-refresh", on_click=state.refresh)

    if state.open:
        kind = state.kind
        cache = state.items[kind]
        if state.error:
            st.error(f"Could not load {kind}s: {state.error}")
            return state.current
        with st.spinner("Loading..."):
            page_items, has_more = cache.select()
        choices = {item.value_subject: item for item in page_items}
        radio_key = f"{key}-{kind}-radio-{cache.page}"
        st.session_state[radio_key] = None
        st.radio(
            kind.capitalize(),
            choices,
            index=None,
            key=radio_key,
            label_visibility="collapsed",
            on_change=_pick,
            args=(state, choices, radio_key),
        )

        prev, item, next_ = st.columns(3, vertical_alignment="center")
        prev.button(
            "Prev",
            key=f"{key}-prev",
            disabled=cache.page == 0,
            width="stretch",
            on_click=state.prev_page,
        )
        item.button(
            cache.page_str(),
            key=f"{key}-page",
            disabled=True,
            width="stretch",
        )
        next_.button(
            "Next",
            key=f"{key}-next",
            disabled=not has_more,
            width="stretch",
            on_click=state.next_page,
        )

    return state.current
