"""Pictures, shapes, and text boxes in XLSX drawings."""

from __future__ import annotations

import re
from typing import Any

from duddysheet.core.drawings import IMAGE_TYPES, SHAPES, Drawing, image_format
from duddysheet.io.xlsx_package import (
    A_NS,
    EMU_PER_PIXEL,
    RELATIONSHIPS_NS,
    XDR_NS,
    XlsxPackage,
    drawing_anchors,
    xml_text,
)

IMAGE_REL = f"{RELATIONSHIPS_NS}/image"


def add_drawings(package: XlsxPackage, workbook: Any) -> None:
    """Write each sheet's pictures, shapes, and text boxes."""
    parts = package.sheet_parts()
    for sheet in workbook:
        if not sheet.drawings or sheet.name not in parts:
            continue
        drawing_part = package.drawing_for(parts[sheet.name])
        for item in sheet.drawings:
            shape_id = package.next_shape_id(drawing_part)
            if item.kind == "picture":
                extension = "jpeg" if item.image_format == "jpeg" else item.image_format
                media = package.next_part("xl/media/image{}." + extension)
                package.entries[media] = item.image
                package.add_default(extension, IMAGE_TYPES[item.image_format])
                rel_id = package.add_relationship(drawing_part, IMAGE_REL, media)
                body = _picture_xml(item, shape_id, rel_id)
            else:
                body = _shape_xml(item, shape_id)
            package.add_anchor(drawing_part, _one_cell_anchor(item, body))


def _emu(pixels: float) -> int:
    return int(round(pixels * EMU_PER_PIXEL))


def _one_cell_anchor(item: Drawing, body: str) -> str:
    namespaces = f'xmlns:xdr="{XDR_NS}" xmlns:a="{A_NS}" xmlns:r="{RELATIONSHIPS_NS}"'
    return (
        f"<xdr:oneCellAnchor {namespaces}>"
        f"<xdr:from><xdr:col>{item.column}</xdr:col><xdr:colOff>{_emu(item.column_offset)}</xdr:colOff>"
        f"<xdr:row>{item.row}</xdr:row><xdr:rowOff>{_emu(item.row_offset)}</xdr:rowOff></xdr:from>"
        f'<xdr:ext cx="{_emu(item.width)}" cy="{_emu(item.height)}"/>{body}<xdr:clientData/></xdr:oneCellAnchor>'
    )


def _transform(item: Drawing) -> str:
    return f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{_emu(item.width)}" cy="{_emu(item.height)}"/></a:xfrm>'


def _color(value: str) -> str:
    return value.lstrip("#").upper()


def _picture_xml(item: Drawing, shape_id: int, rel_id: str) -> str:
    description = f' descr="{xml_text(item.description)}"' if item.description else ""
    return (
        f'<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="{shape_id}" name="{xml_text(item.name)}"{description}/>'
        '<xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr>'
        f'<xdr:blipFill><a:blip r:embed="{rel_id}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
        f'<xdr:spPr>{_transform(item)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic>'
    )


def _shape_xml(item: Drawing, shape_id: int) -> str:
    geometry = "rect" if item.kind == "textbox" else item.shape
    text_box = ' txBox="1"' if item.kind == "textbox" else ""
    fill = "<a:noFill/>" if not item.fill or item.shape == "line" else f'<a:solidFill><a:srgbClr val="{_color(item.fill)}"/></a:solidFill>'
    line = "<a:ln><a:noFill/></a:ln>" if not item.line else f'<a:ln w="9525"><a:solidFill><a:srgbClr val="{_color(item.line)}"/></a:solidFill></a:ln>'
    anchor = "t" if item.kind == "textbox" else "ctr"
    align = "l" if item.kind == "textbox" else "ctr"
    size = int(round(item.font_size * 100))
    run_properties = f'<a:rPr lang="en-US" sz="{size}"><a:solidFill><a:srgbClr val="{_color(item.font_color)}"/></a:solidFill></a:rPr>'
    paragraphs = "".join(
        f'<a:p><a:pPr algn="{align}"/>'
        + (f"<a:r>{run_properties}<a:t>{xml_text(line_text)}</a:t></a:r>" if line_text else "")
        + f'<a:endParaRPr lang="en-US" sz="{size}"/></a:p>'
        for line_text in (item.text.split("\n") if item.text else [""])
    )
    description = f' descr="{xml_text(item.description)}"' if item.description else ""
    return (
        f'<xdr:sp macro="" textlink=""><xdr:nvSpPr><xdr:cNvPr id="{shape_id}" name="{xml_text(item.name)}"{description}/>'
        f"<xdr:cNvSpPr{text_box}/></xdr:nvSpPr>"
        f'<xdr:spPr>{_transform(item)}<a:prstGeom prst="{geometry}"><a:avLst/></a:prstGeom>{fill}{line}</xdr:spPr>'
        f'<xdr:txBody><a:bodyPr vertOverflow="clip" horzOverflow="clip" rtlCol="0" anchor="{anchor}"/><a:lstStyle/>{paragraphs}</xdr:txBody></xdr:sp>'
    )


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def read_drawings(package: XlsxPackage, sheet_part: str, sheet: Any, warnings: list[str]) -> None:
    """Read pictures, shapes, and text boxes from a worksheet's drawing."""
    drawing_part = package.drawing_for(sheet_part, create=False)
    if drawing_part is None or drawing_part not in package.entries:
        return
    targets = {rel_id: target for rel_id, _type, target in package.relationships(drawing_part)}
    approximated = 0
    for anchor in drawing_anchors(package.text(drawing_part)):
        if "graphicFrame" in anchor or "AlternateContent" in anchor:
            continue  # charts are read separately
        position = re.search(
            r"<(?:\w+:)?from>\s*<(?:\w+:)?col>(\d+)</(?:\w+:)?col>\s*<(?:\w+:)?colOff>(-?\d+)</(?:\w+:)?colOff>"
            r"\s*<(?:\w+:)?row>(\d+)</(?:\w+:)?row>\s*<(?:\w+:)?rowOff>(-?\d+)</(?:\w+:)?rowOff>",
            anchor,
        )
        extent = re.search(r'<a:ext\s+cx="(\d+)"\s+cy="(\d+)"', anchor) or re.search(r'<(?:\w+:)?ext\s+cx="(\d+)"\s+cy="(\d+)"', anchor)
        if position is None or extent is None:
            continue
        column, column_offset, row, row_offset = (int(value) for value in position.groups())
        width = max(1.0, int(extent.group(1)) / EMU_PER_PIXEL)
        height = max(1.0, int(extent.group(2)) / EMU_PER_PIXEL)
        name_match = re.search(r'<(?:\w+:)?cNvPr\b[^>]*\bname="([^"]*)"', anchor)
        name = _unescape(name_match.group(1)) if name_match else f"Object {len(sheet.drawings) + 1}"
        description_match = re.search(r'<(?:\w+:)?cNvPr\b[^>]*\bdescr="([^"]*)"', anchor)
        description = _unescape(description_match.group(1)) if description_match else ""
        common = {
            "name": name,
            "row": row,
            "column": column,
            "width": width,
            "height": height,
            "row_offset": row_offset / EMU_PER_PIXEL,
            "column_offset": column_offset / EMU_PER_PIXEL,
            "description": description,
        }
        if re.search(r"<(?:\w+:)?pic\b", anchor):
            embed = re.search(r'r:embed="([^"]+)"', anchor)
            target = targets.get(embed.group(1)) if embed else None
            data = package.entries.get(target, b"") if target else b""
            kind = image_format(data)
            if not kind:
                warnings.append(f"A picture on sheet {sheet.name!r} is not PNG, JPEG, GIF, or BMP and was dropped.")
                continue
            sheet.drawings.append(Drawing(kind="picture", image=data, image_format=kind, **common))
            continue
        if not re.search(r"<(?:\w+:)?sp\b", anchor):
            continue
        geometry = re.search(r'prstGeom\s+prst="(\w+)"', anchor)
        shape = geometry.group(1) if geometry else "rect"
        text_box = bool(re.search(r'cNvSpPr\b[^>]*\btxBox="1"', anchor))
        if not text_box and shape not in SHAPES:
            approximated += 1
            shape = "rect"
        properties = re.search(r"<(?:\w+:)?spPr>(.*?)</(?:\w+:)?spPr>", anchor, re.DOTALL)
        shape_properties = properties.group(1) if properties else ""
        fill = re.search(r'^(?:(?!<a:ln).)*?<a:solidFill><a:srgbClr val="([0-9A-Fa-f]{6})"', shape_properties, re.DOTALL)
        line = re.search(r'<a:ln\b[^>]*>.*?<a:srgbClr val="([0-9A-Fa-f]{6})"', shape_properties, re.DOTALL)
        no_fill = "<a:noFill/>" in shape_properties.split("<a:ln")[0]
        no_line = bool(re.search(r"<a:ln\b[^>]*>\s*<a:noFill/>", shape_properties))
        paragraphs = re.findall(r"<a:p>(.*?)</a:p>", anchor, re.DOTALL)
        text = "\n".join("".join(_unescape(part) for part in re.findall(r"<a:t>([^<]*)</a:t>", paragraph)) for paragraph in paragraphs)
        size = re.search(r'<a:rPr\b[^>]*\bsz="(\d+)"', anchor)
        font_color = re.search(r"<a:rPr\b[^>]*>\s*<a:solidFill><a:srgbClr val=\"([0-9A-Fa-f]{6})\"", anchor)
        defaults = Drawing("x", "textbox" if text_box else "shape", 0, 0, 1, 1)
        if text_box:
            defaults = Drawing("x", "textbox", 0, 0, 1, 1, fill="#ffffff", line="#000000", font_color="#000000")
        sheet.drawings.append(
            Drawing(
                kind="textbox" if text_box else "shape",
                shape="rect" if text_box else shape,
                text=text.rstrip("\n"),
                fill="" if no_fill else ("#" + fill.group(1).lower() if fill else defaults.fill),
                line="" if no_line else ("#" + line.group(1).lower() if line else defaults.line),
                font_color="#" + font_color.group(1).lower() if font_color else defaults.font_color,
                font_size=int(size.group(1)) / 100 if size else defaults.font_size,
                **common,
            )
        )
    if approximated:
        warnings.append(f"{approximated} shape(s) on sheet {sheet.name!r} have no Duddy Spreadsheet equivalent and were imported as rectangles.")


def _unescape(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
