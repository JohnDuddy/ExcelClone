"""Edit a saved XLSX package: parts, relationships, content types, drawings.

openpyxl writes the core of every workbook. Excel features it cannot write
(Office 2016 charts, sparklines, PivotTables, shapes) are added afterwards by
editing the saved ZIP package through this class.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DRAWING_REL = f"{RELATIONSHIPS_NS}/drawing"
DRAWING_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.drawing+xml"
XDR_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

# Child elements that must follow <drawing> inside <worksheet>, in order.
_AFTER_DRAWING = (
    "legacyDrawing",
    "legacyDrawingHF",
    "drawingHF",
    "picture",
    "oleObjects",
    "controls",
    "webPublishItems",
    "tableParts",
    "extLst",
)
# Child elements that must follow <pivotCaches> inside <workbook>.
_AFTER_PIVOT_CACHES = (
    "smartTagPr",
    "smartTagTypes",
    "webPublishing",
    "fileRecoveryPr",
    "webPublishObjects",
    "extLst",
)
EMU_PER_PIXEL = 9525


def xml_text(value: object) -> str:
    """Escape ``value`` for XML text and attribute content."""
    return escape(str(value), {'"': "&quot;"})


def quote_sheet(name: str) -> str:
    """Return ``name`` quoted for use in a formula reference when needed."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", name) and not re.fullmatch(
        r"[A-Za-z]{1,3}[0-9]+", name
    ):
        return name
    return "'" + name.replace("'", "''") + "'"


class XlsxPackage:
    """In-memory view of an XLSX ZIP package that can be edited and saved."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with zipfile.ZipFile(self.path) as archive:
            self.entries: dict[str, bytes] = {
                name: archive.read(name) for name in archive.namelist()
            }

    # -- basic parts -------------------------------------------------------
    def text(self, part: str) -> str:
        """Return a part's XML as text."""
        return self.entries[part].decode("utf-8")

    def set_text(self, part: str, xml: str) -> None:
        """Replace or create a part."""
        self.entries[part] = xml.encode("utf-8")

    def next_part(self, pattern: str) -> str:
        """Return the first unused part name for ``pattern`` (with ``{}``)."""
        number = 1
        while pattern.format(number) in self.entries:
            number += 1
        return pattern.format(number)

    def save(self) -> None:
        """Write the package back to disk."""
        with zipfile.ZipFile(self.path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in self.entries.items():
                archive.writestr(name, data)

    # -- content types -----------------------------------------------------
    def add_override(self, part: str, content_type: str) -> None:
        """Register ``part`` with an explicit content type."""
        types = self.text("[Content_Types].xml")
        name = "/" + part
        if f'PartName="{name}"' in types:
            return
        types = types.replace(
            "</Types>",
            f'<Override PartName="{name}" ContentType="{content_type}"/></Types>',
        )
        self.set_text("[Content_Types].xml", types)

    def add_default(self, extension: str, content_type: str) -> None:
        """Register a content type for every part with ``extension``."""
        types = self.text("[Content_Types].xml")
        if re.search(rf'Extension="{re.escape(extension)}"', types, re.IGNORECASE):
            return
        types = re.sub(
            r"(<Types[^>]*>)",
            rf'\1<Default Extension="{extension}" ContentType="{content_type}"/>',
            types,
            count=1,
        )
        self.set_text("[Content_Types].xml", types)

    # -- relationships -----------------------------------------------------
    @staticmethod
    def rels_part(part: str) -> str:
        """Return the relationships part that belongs to ``part``."""
        folder, name = posixpath.split(part)
        return posixpath.join(folder, "_rels", name + ".rels")

    def relationships(self, part: str) -> list[tuple[str, str, str]]:
        """Return ``(id, type, absolute target)`` for each relationship."""
        rels = self.rels_part(part)
        if rels not in self.entries:
            return []
        folder = posixpath.dirname(part)
        result = []
        for match in re.finditer(r"<Relationship\b([^>]*)/?>", self.text(rels)):
            attributes = dict(re.findall(r'(\w+)="([^"]*)"', match.group(1)))
            target = attributes.get("Target", "")
            if attributes.get("TargetMode") == "External":
                absolute = target
            elif target.startswith("/"):
                absolute = target[1:]
            else:
                absolute = posixpath.normpath(posixpath.join(folder, target))
            result.append((attributes.get("Id", ""), attributes.get("Type", ""), absolute))
        return result

    def add_relationship(self, part: str, rel_type: str, target: str) -> str:
        """Add a relationship from ``part`` to the absolute part ``target``."""
        rels = self.rels_part(part)
        if rels not in self.entries:
            self.set_text(
                rels,
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                f'<Relationships xmlns="{PACKAGE_RELATIONSHIPS_NS}"></Relationships>',
            )
        xml = self.text(rels)
        used = set(re.findall(r'Id="([^"]*)"', xml))
        number = 1
        while f"rId{number}" in used:
            number += 1
        identifier = f"rId{number}"
        xml = xml.replace(
            "</Relationships>",
            f'<Relationship Id="{identifier}" Type="{rel_type}" Target="/{target}"/></Relationships>',
        )
        self.set_text(rels, xml)
        return identifier

    def target_of(self, part: str, identifier: str) -> str | None:
        """Return the absolute target of relationship ``identifier``."""
        for rel_id, _rel_type, target in self.relationships(part):
            if rel_id == identifier:
                return target
        return None

    # -- workbook and sheets -----------------------------------------------
    def sheet_parts(self) -> dict[str, str]:
        """Map each sheet name to its worksheet part."""
        workbook = self.text("xl/workbook.xml")
        targets = {rel_id: target for rel_id, _type, target in self.relationships("xl/workbook.xml")}
        result: dict[str, str] = {}
        for match in re.finditer(r"<(?:\w+:)?sheet\b([^>]*)/>", workbook):
            attributes = match.group(1)
            name = re.search(r'\bname="([^"]*)"', attributes)
            rel_id = re.search(r'\br:id="([^"]*)"', attributes)
            if name and rel_id and rel_id.group(1) in targets:
                result[_unescape(name.group(1))] = targets[rel_id.group(1)]
        return result

    def number_formats(self) -> dict[int, str]:
        """Return number format codes by id: built-in ones and the file's own."""
        from openpyxl.styles.numbers import BUILTIN_FORMATS

        formats = dict(BUILTIN_FORMATS)
        if "xl/styles.xml" in self.entries:
            for identifier, code in re.findall(
                r'<(?:\w+:)?numFmt\b[^>]*\bnumFmtId="(\d+)"[^>]*\bformatCode="([^"]*)"', self.text("xl/styles.xml")
            ):
                formats[int(identifier)] = _unescape(code)
        return formats

    def number_format_id(self, code: str) -> int:
        """Return the id of number format ``code``, adding it to the styles if new."""
        formats = self.number_formats()
        for identifier, existing in formats.items():
            if existing == code:
                return identifier
        identifier = max([163, *formats]) + 1
        styles = self.text("xl/styles.xml")
        entry = f'<numFmt numFmtId="{identifier}" formatCode="{xml_text(code)}"/>'
        found = re.search(r"<((?:\w+:)?)numFmts\b[^>]*>", styles)
        if found:
            closing = f"</{found.group(1)}numFmts>"
            styles = styles.replace(closing, entry + closing, 1)
            count = len(re.findall(r"<(?:\w+:)?numFmt\b", styles))
            styles = re.sub(r'(<(?:\w+:)?numFmts\b[^>]*\bcount=")\d+', rf"\g<1>{count}", styles, count=1)
        else:
            styles = re.sub(
                r"(<(?:\w+:)?styleSheet\b[^>]*>)",
                lambda match: f'{match.group(1)}<numFmts count="1">{entry}</numFmts>',
                styles,
                count=1,
            )
        self.set_text("xl/styles.xml", styles)
        return identifier

    def defined_names(self) -> dict[str, str]:
        """Return the workbook's defined names and the text they refer to."""
        workbook = self.text("xl/workbook.xml")
        return {
            _unescape(name): _unescape(value)
            for name, value in re.findall(
                r'<(?:\w+:)?definedName\b[^>]*\bname="([^"]+)"[^>]*>([^<]*)</(?:\w+:)?definedName>', workbook
            )
        }

    def insert_drawing_element(self, sheet_part: str, xml: str) -> None:
        """Insert a worksheet ``<drawing>`` element at its schema position."""
        self.set_text(sheet_part, _insert_before(self.text(sheet_part), _AFTER_DRAWING, "worksheet", xml))

    def add_worksheet_extension(self, sheet_part: str, ext_xml: str) -> None:
        """Append an ``<ext>`` element to the worksheet's ``<extLst>``."""
        xml = self.text(sheet_part)
        closing = re.search(r"</(\w+:)?extLst>\s*</(\w+:)?worksheet>\s*$", xml)
        if closing:
            xml = xml[: closing.start()] + ext_xml + xml[closing.start() :]
        else:
            xml = re.sub(r"</((\w+:)?)worksheet>\s*$", rf"<\1extLst>{ext_xml}</\1extLst></\1worksheet>", xml)
        self.set_text(sheet_part, xml)

    def add_pivot_cache(self, cache_id: int, definition_part: str) -> None:
        """Register a pivot cache definition with the workbook."""
        rel_id = self.add_relationship(
            "xl/workbook.xml",
            f"{RELATIONSHIPS_NS}/pivotCacheDefinition",
            definition_part,
        )
        xml = self.text("xl/workbook.xml")
        entry = (
            f'<pivotCache xmlns:r="{RELATIONSHIPS_NS}" cacheId="{cache_id}" r:id="{rel_id}"/>'
        )
        if re.search(r"</(\w+:)?pivotCaches>", xml):
            xml = re.sub(r"(</(\w+:)?pivotCaches>)", entry + r"\1", xml, count=1)
        else:
            xml = _insert_before(xml, _AFTER_PIVOT_CACHES, "workbook", f"<pivotCaches>{entry}</pivotCaches>")
        self.set_text("xl/workbook.xml", xml)

    # -- drawings ------------------------------------------------------------
    def drawing_for(self, sheet_part: str, *, create: bool = True) -> str | None:
        """Return the sheet's drawing part, creating an empty one if needed."""
        for _rel_id, rel_type, target in self.relationships(sheet_part):
            if rel_type == DRAWING_REL:
                return target
        if not create:
            return None
        drawing = self.next_part("xl/drawings/drawing{}.xml")
        self.set_text(
            drawing,
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<xdr:wsDr xmlns:xdr="{XDR_NS}" xmlns:a="{A_NS}"></xdr:wsDr>',
        )
        self.add_override(drawing, DRAWING_CONTENT_TYPE)
        rel_id = self.add_relationship(sheet_part, DRAWING_REL, drawing)
        self.insert_drawing_element(sheet_part, f'<drawing xmlns:r="{RELATIONSHIPS_NS}" r:id="{rel_id}"/>')
        return drawing

    def next_shape_id(self, drawing_part: str) -> int:
        """Return an unused ``cNvPr`` id within a drawing."""
        ids = [int(value) for value in re.findall(r'<(?:\w+:)?cNvPr\b[^>]*\bid="(\d+)"', self.text(drawing_part))]
        return max(ids, default=0) + 1

    def add_anchor(self, drawing_part: str, anchor_xml: str) -> None:
        """Append an anchor element to a drawing."""
        xml = self.text(drawing_part)
        xml = re.sub(r"(</(\w+:)?wsDr>\s*)$", anchor_xml.replace("\\", "\\\\") + r"\1", xml)
        self.set_text(drawing_part, xml)


def two_cell_anchor(
    left: int,
    top: int,
    right: int,
    bottom: int,
    body: str,
    *,
    edit_as: str = "oneCell",
    offsets: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> str:
    """Return a ``<xdr:twoCellAnchor>`` spanning zero-based cell bounds."""
    namespaces = f'xmlns:xdr="{XDR_NS}" xmlns:a="{A_NS}" xmlns:r="{RELATIONSHIPS_NS}"'
    return (
        f'<xdr:twoCellAnchor {namespaces} editAs="{edit_as}">'
        f"<xdr:from><xdr:col>{left}</xdr:col><xdr:colOff>{offsets[0]}</xdr:colOff>"
        f"<xdr:row>{top}</xdr:row><xdr:rowOff>{offsets[1]}</xdr:rowOff></xdr:from>"
        f"<xdr:to><xdr:col>{right}</xdr:col><xdr:colOff>{offsets[2]}</xdr:colOff>"
        f"<xdr:row>{bottom}</xdr:row><xdr:rowOff>{offsets[3]}</xdr:rowOff></xdr:to>"
        f"{body}<xdr:clientData/></xdr:twoCellAnchor>"
    )


def anchor_bounds(xml: str) -> tuple[int, int, int, int, tuple[int, int, int, int]] | None:
    """Return ``(left, top, right, bottom, offsets)`` of a two-cell anchor."""
    found = re.search(
        r"<(?:\w+:)?from>\s*<(?:\w+:)?col>(\d+)</(?:\w+:)?col>\s*<(?:\w+:)?colOff>(-?\d+)</(?:\w+:)?colOff>"
        r"\s*<(?:\w+:)?row>(\d+)</(?:\w+:)?row>\s*<(?:\w+:)?rowOff>(-?\d+)</(?:\w+:)?rowOff>\s*</(?:\w+:)?from>"
        r"\s*<(?:\w+:)?to>\s*<(?:\w+:)?col>(\d+)</(?:\w+:)?col>\s*<(?:\w+:)?colOff>(-?\d+)</(?:\w+:)?colOff>"
        r"\s*<(?:\w+:)?row>(\d+)</(?:\w+:)?row>\s*<(?:\w+:)?rowOff>(-?\d+)</(?:\w+:)?rowOff>",
        xml,
    )
    if not found:
        return None
    left, left_off, top, top_off, right, right_off, bottom, bottom_off = (int(value) for value in found.groups())
    return left, top, right, bottom, (left_off, top_off, right_off, bottom_off)


def drawing_anchors(xml: str) -> list[str]:
    """Split a drawing part into its top-level anchor elements."""
    return [
        match.group(0)
        for match in re.finditer(
            r"<((?:\w+:)?(?:twoCellAnchor|oneCellAnchor|absoluteAnchor))\b.*?</\1>",
            xml,
            re.DOTALL,
        )
    ]


def _insert_before(xml: str, followers: tuple[str, ...], root: str, fragment: str) -> str:
    positions = [
        match.start()
        for name in followers
        for match in [re.search(rf"<(\w+:)?{name}[\s>/]", xml)]
        if match
    ]
    if positions:
        position = min(positions)
        return xml[:position] + fragment + xml[position:]
    closing = re.search(rf"</(\w+:)?{root}>\s*$", xml)
    if closing is None:
        raise ValueError(f"Malformed {root} part")
    return xml[: closing.start()] + fragment + xml[closing.start() :]


def _unescape(text: str) -> str:
    return (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )
