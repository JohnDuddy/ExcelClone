"""Mark spilled formulas as Excel dynamic arrays inside a saved XLSX package.

Excel distinguishes a dynamic-array formula from a legacy array formula by
cell metadata: the anchor cell carries ``cm="1"``, pointing at an
``XLDAPR`` record in ``xl/metadata.xml``. openpyxl writes array formulas but
not this metadata, so it is added here after saving.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

_METADATA = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<metadata xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:xda="http://schemas.microsoft.com/office/spreadsheetml/2017/dynamicarray">'
    '<metadataTypes count="1"><metadataType name="XLDAPR" minSupportedVersion="120000" '
    'copy="1" pasteAll="1" pasteValues="1" merge="1" splitFirst="1" rowColShift="1" '
    'clearFormats="1" clearComments="1" assign="1" coerce="1" cellMeta="1"/></metadataTypes>'
    '<futureMetadata name="XLDAPR" count="1"><bk><extLst>'
    '<ext uri="{bdbb8cdc-fa1e-496e-a857-3c3f30c029c3}">'
    '<xda:dynamicArrayProperties fDynamic="1" fCollapsed="0"/></ext></extLst></bk>'
    "</futureMetadata>"
    '<cellMetadata count="1"><bk><rc t="1" v="0"/></bk></cellMetadata></metadata>'
)
_CONTENT_TYPE = (
    '<Override PartName="/xl/metadata.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheetMetadata+xml"/>'
)
_RELATIONSHIP_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sheetMetadata"
)


def mark_dynamic_arrays(path: str | Path, anchors: dict[str, set[str]]) -> None:
    """Add dynamic-array metadata for ``anchors`` (sheet name -> A1 cells)."""
    if not any(anchors.values()):
        return
    destination = Path(path)
    with zipfile.ZipFile(destination) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
        infos = {info.filename: info for info in archive.infolist()}
    sheet_parts = _sheet_parts(entries)
    changed = False
    for sheet_name, cells in anchors.items():
        part = sheet_parts.get(sheet_name)
        if part is None or not cells or part not in entries:
            continue
        xml = entries[part].decode("utf-8")
        for reference in cells:
            pattern = re.compile(rf'<c r="{re.escape(reference)}"(?![^>]*\bcm=)')
            xml, count = pattern.subn(f'<c r="{reference}" cm="1"', xml, count=1)
            changed = changed or bool(count)
        entries[part] = xml.encode("utf-8")
    if not changed:
        return
    entries["xl/metadata.xml"] = _METADATA.encode("utf-8")
    content_types = entries["[Content_Types].xml"].decode("utf-8")
    if "/xl/metadata.xml" not in content_types:
        content_types = content_types.replace("</Types>", _CONTENT_TYPE + "</Types>")
        entries["[Content_Types].xml"] = content_types.encode("utf-8")
    relationships = entries["xl/_rels/workbook.xml.rels"].decode("utf-8")
    if _RELATIONSHIP_TYPE not in relationships:
        used = {int(value) for value in re.findall(r'Id="rId(\d+)"', relationships)}
        identifier = max(used, default=0) + 1
        relationships = relationships.replace(
            "</Relationships>",
            f'<Relationship Type="{_RELATIONSHIP_TYPE}" Target="metadata.xml" '
            f'Id="rId{identifier}" /></Relationships>',
        )
        entries["xl/_rels/workbook.xml.rels"] = relationships.encode("utf-8")
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            info = infos.get(name)
            if info is not None:
                clone = zipfile.ZipInfo(name, date_time=info.date_time)
                clone.compress_type = zipfile.ZIP_DEFLATED
                clone.external_attr = info.external_attr
                archive.writestr(clone, data)
            else:
                archive.writestr(name, data)
    temporary.replace(destination)


def _sheet_parts(entries: dict[str, bytes]) -> dict[str, str]:
    """Map sheet names to their worksheet part paths."""
    workbook = entries.get("xl/workbook.xml", b"").decode("utf-8")
    relationships = entries.get("xl/_rels/workbook.xml.rels", b"").decode("utf-8")
    targets = {
        identifier: target
        for target, identifier in re.findall(
            r'<Relationship[^>]*Target="([^"]+)"[^>]*Id="([^"]+)"',
            relationships,
        )
    }
    targets.update(
        {
            identifier: target
            for identifier, target in re.findall(
                r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"',
                relationships,
            )
        }
    )
    parts: dict[str, str] = {}
    for match in re.finditer(r"<sheet\b[^>]*>", workbook):
        tag = match.group(0)
        name = re.search(r'name="([^"]*)"', tag)
        identifier = re.search(r'r:id="([^"]+)"', tag) or re.search(r'\bid="([^"]+)"', tag)
        if not name or not identifier:
            continue
        target = targets.get(identifier.group(1), "")
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        parts[_unescape(name.group(1))] = target
    return parts


def _unescape(value: str) -> str:
    return (
        value.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )
