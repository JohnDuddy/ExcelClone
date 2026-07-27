"""Generate the multi-resolution Duddy Spreadsheet Windows icon using only stdlib."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZES = (16, 32, 48, 256)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _png(width: int, height: int, pixels: bytes) -> bytes:
    rows = b"".join(
        b"\x00" + pixels[row * width * 4 : (row + 1) * width * 4]
        for row in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0),
        )
        + _png_chunk(b"IDAT", zlib.compress(rows, 9))
        + _png_chunk(b"IEND", b"")
    )


def _render(size: int) -> bytes:
    scale = 4
    canvas_size = size * scale
    pixels = bytearray(canvas_size * canvas_size * 4)

    def set_pixel(x: int, y: int, color: tuple[int, int, int, int]) -> None:
        if 0 <= x < canvas_size and 0 <= y < canvas_size:
            offset = (y * canvas_size + x) * 4
            pixels[offset : offset + 4] = bytes(color)

    def rectangle(
        left: int,
        top: int,
        right: int,
        bottom: int,
        color: tuple[int, int, int, int],
    ) -> None:
        for y in range(max(0, top), min(canvas_size, bottom)):
            for x in range(max(0, left), min(canvas_size, right)):
                set_pixel(x, y, color)

    def rounded_square(
        inset: int,
        radius: int,
        color: tuple[int, int, int, int],
    ) -> None:
        low = inset
        high = canvas_size - inset
        for y in range(low, high):
            for x in range(low, high):
                dx = max(low + radius - x, 0, x - (high - radius - 1))
                dy = max(low + radius - y, 0, y - (high - radius - 1))
                if dx * dx + dy * dy <= radius * radius:
                    set_pixel(x, y, color)

    rounded_square(1 * scale, 4 * scale, (22, 82, 64, 255))
    rounded_square(2 * scale, 3 * scale, (28, 112, 82, 255))
    margin = 4 * scale
    gap = max(scale, round(1.1 * scale))
    grid_size = canvas_size - margin * 2
    cell = (grid_size - gap * 2) // 3
    cream = (240, 238, 220, 255)
    gold = (244, 183, 64, 255)
    for row in range(3):
        for column in range(3):
            left = margin + column * (cell + gap)
            top = margin + row * (cell + gap)
            color = gold if (row, column) == (0, 2) else cream
            rectangle(left, top, left + cell, top + cell, color)

    # A rising green trace across the cells gives the grid its own identity.
    trace = (14, 70, 52, 255)
    points = (
        (margin + cell // 2, margin + 2 * (cell + gap) + cell // 2),
        (margin + cell + gap + cell // 2, margin + cell + gap + cell // 2),
        (margin + 2 * (cell + gap) + cell // 2, margin + cell // 2),
    )
    thickness = max(scale, size // 18 * scale)
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for step in range(steps + 1):
            x = round(x0 + (x1 - x0) * step / steps)
            y = round(y0 + (y1 - y0) * step / steps)
            rectangle(
                x - thickness // 2,
                y - thickness // 2,
                x + (thickness + 1) // 2,
                y + (thickness + 1) // 2,
                trace,
            )

    downsampled = bytearray(size * size * 4)
    samples = scale * scale
    for y in range(size):
        for x in range(size):
            totals = [0, 0, 0, 0]
            for sample_y in range(scale):
                for sample_x in range(scale):
                    source = (
                        ((y * scale + sample_y) * canvas_size)
                        + x * scale
                        + sample_x
                    ) * 4
                    for channel in range(4):
                        totals[channel] += pixels[source + channel]
            target = (y * size + x) * 4
            downsampled[target : target + 4] = bytes(
                round(total / samples) for total in totals
            )
    return _png(size, size, bytes(downsampled))


def generate_icon(destination: str | Path | None = None) -> Path:
    """Write a valid ICO containing 16, 32, 48, and 256 px PNG frames."""
    path = (
        Path(destination)
        if destination is not None
        else Path(__file__).resolve().parent / "assets" / "duddysheet.ico"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    images = [_render(size) for size in SIZES]
    header_size = 6 + 16 * len(images)
    offset = header_size
    entries: list[bytes] = []
    for size, image in zip(SIZES, images):
        encoded_size = 0 if size == 256 else size
        entries.append(
            struct.pack(
                "<BBBBHHII",
                encoded_size,
                encoded_size,
                0,
                0,
                1,
                32,
                len(image),
                offset,
            )
        )
        offset += len(image)
    path.write_bytes(
        struct.pack("<HHH", 0, 1, len(images))
        + b"".join(entries)
        + b"".join(images)
    )
    return path


if __name__ == "__main__":
    print(generate_icon())
