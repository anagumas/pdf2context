"""Minimal PDF writer for tests. Standard Helvetica only."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence


def make_pdf(path: Path, pages: Sequence[Optional[str]]) -> None:
    """Write a PDF. None creates a page with no text."""
    font_number = 3 + len(pages) * 2
    kids = []
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
    }
    next_number = 3
    for text in pages:
        page_number = next_number
        content_number = next_number + 1
        next_number += 2
        kids.append(page_number)
        objects[page_number] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_number} 0 R /Resources << /Font << /F1 {font_number} 0 R >> >> >>"
        ).encode()
        objects[content_number] = _content(text)
    objects[2] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{kid} 0 R' for kid in kids)}] /Count {len(pages)} >>"
    ).encode()
    objects[font_number] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    output = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(output)
        output += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    xref = len(output)
    size = max(objects) + 1
    output += f"xref\n0 {size}\n".encode()
    output += b"0000000000 65535 f \n"
    for number in range(1, size):
        output += f"{offsets[number]:010d} 00000 n \n".encode()
    output += (
        f"trailer << /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output)


def _content(text: Optional[str]) -> bytes:
    if text is None:
        return b"<< /Length 0 >>\nstream\nendstream"
    literal = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 24 Tf 72 720 Td ({literal}) Tj ET".encode()
    return b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
