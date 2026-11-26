"""Threaded comments in XLSX, stored the way Excel 365 stores them.

Excel keeps a thread in ``xl/threadedComments``, its authors in
``xl/persons/person.xml``, and a legacy comment on the same cell so older
Excel versions can still read it. The legacy comment is written by openpyxl
(see ``legacy_comment``); the threaded parts are added to the package here.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from openpyxl.comments import Comment

from duddysheet.core.comments import CommentEntry, CommentThread
from duddysheet.core.refs import CellReference
from duddysheet.io.xlsx_package import XlsxPackage, xml_text

THREADED_NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PERSON_REL = "http://schemas.microsoft.com/office/2017/10/relationships/person"
THREAD_REL = "http://schemas.microsoft.com/office/2017/10/relationships/threadedComment"
LEGACY_PREFIX = "[Threaded comment]"
_LEGACY_NOTICE = (
    "[Threaded comment]\n\nYour version of Excel allows you to read this threaded comment; "
    "however, any edits to it will get removed if the file is opened in a newer version of Excel. "
    "Learn more: https://go.microsoft.com/fwlink/?linkid=870924\n\n"
)


def _guid(*parts: object) -> str:
    return "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, "/".join(str(part) for part in parts))).upper() + "}"


def legacy_comment(sheet_name: str, row: int, column: int, thread: CommentThread) -> Comment:
    """Return the fallback comment Excel writes beside a threaded comment."""
    lines = [_LEGACY_NOTICE + "Comment:\n    " + thread.entries[0].text]
    lines.extend("Reply:\n    " + entry.text for entry in thread.entries[1:])
    comment = Comment("\n".join(lines), "tc=" + _guid(sheet_name, row, column, 0))
    comment.width = 200
    comment.height = 100
    return comment


def write_threaded_comments(package: XlsxPackage, workbook: Any) -> None:
    """Add persons and threadedComments parts for every sheet's comment threads."""
    parts = package.sheet_parts()
    people: dict[str, str] = {}
    for sheet in workbook:
        comments = getattr(sheet, "comments", None)
        if not comments or sheet.name not in parts:
            continue
        entries = []
        for (row, column), thread in sorted(comments.items()):
            reference = CellReference(row, column).to_a1(include_sheet=False)
            parent = _guid(sheet.name, row, column, 0)
            for position, entry in enumerate(thread.entries):
                person = people.setdefault(entry.author, _guid("person", entry.author))
                attributes = [
                    f'ref="{reference}"',
                    f'dT="{xml_text(entry.created)}"',
                    f'personId="{person}"',
                    f'id="{_guid(sheet.name, row, column, position)}"',
                ]
                if position:
                    attributes.append(f'parentId="{parent}"')
                elif thread.resolved:
                    attributes.append('done="1"')
                entries.append(f"<threadedComment {' '.join(attributes)}><text>{xml_text(entry.text)}</text></threadedComment>")
        part = package.next_part("xl/threadedComments/threadedComment{}.xml")
        package.set_text(
            part,
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<ThreadedComments xmlns="{THREADED_NS}" xmlns:x="{MAIN_NS}">{"".join(entries)}</ThreadedComments>',
        )
        package.add_override(part, "application/vnd.ms-excel.threadedcomments+xml")
        package.add_relationship(parts[sheet.name], THREAD_REL, part)
    if not people:
        return
    persons = "xl/persons/person.xml"
    package.set_text(
        persons,
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<personList xmlns="{THREADED_NS}" xmlns:x="{MAIN_NS}">'
        + "".join(
            f'<person displayName="{xml_text(name)}" id="{identifier}" userId="{xml_text(name)}" providerId="None"/>'
            for name, identifier in people.items()
        )
        + "</personList>",
    )
    package.add_override(persons, "application/vnd.ms-excel.person+xml")
    package.add_relationship("xl/workbook.xml", PERSON_REL, persons)


def read_threaded_comments(package: XlsxPackage, sheet_part: str, sheet: Any) -> None:
    """Read a sheet's threaded comments and drop their legacy fallback notes."""
    people: dict[str, str] = {}
    for _rel_id, rel_type, target in package.relationships("xl/workbook.xml"):
        if rel_type == PERSON_REL and target in package.entries:
            for match in re.finditer(r"<(?:\w+:)?person\b([^>]*)/?>", package.text(target)):
                attributes = dict(re.findall(r'(\w+)="([^"]*)"', match.group(1)))
                people[attributes.get("id", "")] = _unescape(attributes.get("displayName", "Author"))
    for _rel_id, rel_type, target in package.relationships(sheet_part):
        if rel_type != THREAD_REL or target not in package.entries:
            continue
        threads: dict[str, list[tuple[CellReference, CommentEntry, bool]]] = {}
        order: list[str] = []
        for match in re.finditer(r"<(?:\w+:)?threadedComment\b([^>]*)>(.*?)</(?:\w+:)?threadedComment>", package.text(target), re.DOTALL):
            attributes = dict(re.findall(r'(\w+)="([^"]*)"', match.group(1)))
            text_match = re.search(r"<(?:\w+:)?text>(.*?)</(?:\w+:)?text>", match.group(2), re.DOTALL)
            text = _unescape(text_match.group(1)) if text_match else ""
            if not text.strip():
                continue
            try:
                from duddysheet.core.refs import parse_a1

                cell = parse_a1(attributes.get("ref", ""))
            except (ValueError, KeyError):
                continue
            if not isinstance(cell, CellReference):
                continue
            entry = CommentEntry(people.get(attributes.get("personId", ""), "Author"), text, attributes.get("dT", ""))
            key = attributes.get("parentId") or attributes.get("id", "")
            if key not in threads:
                threads[key] = []
                order.append(key)
            threads[key].append((cell, entry, attributes.get("done") == "1"))
        for key in order:
            items = threads[key]
            cell = items[0][0]
            sheet.comments[(cell.row, cell.column)] = CommentThread(tuple(entry for _cell, entry, _done in items), resolved=any(done for _cell, _entry, done in items))
            note = sheet.notes.get((cell.row, cell.column))
            if note is not None and getattr(note, "text", "").startswith(LEGACY_PREFIX):
                del sheet.notes[(cell.row, cell.column)]


def _unescape(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
