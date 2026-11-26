"""Threaded comments (Review > New Comment): conversations attached to a cell.

Excel 365 keeps threaded comments apart from notes: a comment has replies,
authors, timestamps, and can be marked resolved. Notes stay in
``Sheet.notes``; threads live in ``Sheet.comments``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class CommentEntry:
    """One message in a thread."""

    author: str
    text: str
    created: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("A comment needs some text.")


@dataclass(frozen=True, slots=True)
class CommentThread:
    """A comment and its replies on one cell."""

    entries: tuple[CommentEntry, ...]
    resolved: bool = False

    @property
    def author(self) -> str:
        return self.entries[0].author

    def summary(self) -> str:
        """Return the thread as plain text, oldest first."""
        lines = [f"{entry.author}: {entry.text}" for entry in self.entries]
        if self.resolved:
            lines.append("(Resolved)")
        return "\n".join(lines)


def now() -> str:
    """Return the current UTC time in the ISO form Excel stores."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-4]


def start_thread(text: str, author: str, created: str | None = None) -> CommentThread:
    return CommentThread((CommentEntry(author, text, created or now()),))


def add_reply(thread: CommentThread, text: str, author: str, created: str | None = None) -> CommentThread:
    """Reply to a thread (replying reopens a resolved thread, as in Excel)."""
    return CommentThread(thread.entries + (CommentEntry(author, text, created or now()),), resolved=False)


def set_resolved(thread: CommentThread, resolved: bool) -> CommentThread:
    return replace(thread, resolved=resolved)


def thread_to_dict(thread: CommentThread) -> dict[str, Any]:
    return {
        "entries": [[entry.author, entry.text, entry.created] for entry in thread.entries],
        "resolved": thread.resolved,
    }


def thread_from_dict(data: dict[str, Any]) -> CommentThread:
    return CommentThread(tuple(CommentEntry(*item) for item in data["entries"]), bool(data.get("resolved", False)))


def shift_comments(comments: dict[tuple[int, int], CommentThread], axis: str, index: int, count: int, delete: bool) -> dict[tuple[int, int], CommentThread]:
    """Move threads with inserted or deleted rows/columns; drop threads on deleted cells."""
    moved: dict[tuple[int, int], CommentThread] = {}
    for (row, column), thread in comments.items():
        position = row if axis == "row" else column
        if position >= index:
            if delete:
                if position < index + count:
                    continue
                position -= count
            else:
                position += count
        moved[(position, column) if axis == "row" else (row, position)] = thread
    return moved
