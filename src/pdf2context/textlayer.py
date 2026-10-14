"""Recognition levels 2 and 3: PaddleOCR boxes written back onto the original page."""

from __future__ import annotations

import ctypes
import io
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import pypdfium2 as pdfium
from fontTools.ttLib import TTFont
from fontTools.subset import Subsetter
from fontTools.varLib.instancer import instantiateVariableFont
from pypdfium2 import raw

from pdf2context.messages import say

RECOGNITION_DPI = 300
RECOGNITION_SCALE = RECOGNITION_DPI / 72

_LEVEL_MODELS = {
    2: ("PP-OCRv6_small_det", "PP-OCRv6_small_rec"),
    3: ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"),
}


@dataclass(frozen=True)
class TextBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


def font_search_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / "Library" / "Fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        home / ".local" / "share" / "fonts",
        home / ".fonts",
        Path("/usr/local/share/fonts"),
        Path("/usr/share/fonts"),
        home / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
    ]
    return [root for root in roots if root.is_dir()]


def find_noto_sans_cjk(roots: Optional[Sequence[Path]] = None) -> Optional[Path]:
    """Return one installed Noto Sans CJK file, preferring a Japanese Regular face."""
    found: list[Path] = []
    for root in roots if roots is not None else font_search_roots():
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and _is_noto_sans_cjk(path):
                found.append(path)
    if not found:
        return None
    found.sort(key=_font_rank)
    return found[0]


def write_recognition_layer(
    source: Path,
    dest: Path,
    *,
    mode: str,
    level: int,
    paddle: str,
    font: Path,
    timeout: float,
    runner,
    warn,
    page_text,
) -> None:
    """Write PaddleOCR text onto a copy of `source`. The page image is not redrawn."""
    shutil.copyfile(source, dest)
    pdf = pdfium.PdfDocument(dest)
    rewritten = dest.with_name(dest.name + ".rewritten")
    try:
        recognized: list[tuple[int, list[TextBox]]] = []
        changed = False
        for index in range(len(pdf)):
            text = page_text(dest, index + 1)
            if not _page_needs_ocr(text, mode):
                continue
            page = pdf[index]
            image = page.render(scale=RECOGNITION_SCALE, rotation=0)
            png = dest.with_name(f"{dest.stem}-p{index + 1}.png")
            try:
                image.to_pil().save(png)
                boxes = _recognize_png(png, paddle, level, timeout, runner, warn)
            finally:
                image.close()
                png.unlink(missing_ok=True)
            if mode == "force":
                _drop_text(page)
                changed = True
            if boxes:
                recognized.append((index, boxes))
                changed = True
        if not changed:
            return
        if recognized:
            characters = "".join(box.text for _, boxes in recognized for box in boxes)
            _stamp(pdf, font, recognized, characters)
        pdf.save(rewritten)
    finally:
        pdf.close()
        if rewritten.exists():
            os.replace(rewritten, dest)


def _failure(key: str, **kwargs: object):
    from pdf2context.pipeline import Pdf2ContextError

    raise Pdf2ContextError(say(key, **kwargs))


def parse_recognition_json(payload: object) -> list[TextBox]:
    found = _find_recognition(payload)
    if found is None:
        _failure("paddle_result", detail="rec_texts")
    texts, boxes = found
    if len(texts) != len(boxes):
        _failure("paddle_result", detail="rec_boxes")
    parsed: list[TextBox] = []
    for text, box in zip(texts, boxes):
        if not str(text):
            continue
        if len(box) != 4:
            _failure("paddle_result", detail="rec_boxes")
        x0, y0, x1, y1 = (float(value) for value in box)
        if x1 <= x0 or y1 <= y0:
            continue
        parsed.append(TextBox(str(text), x0, y0, x1, y1))
    return parsed


def _recognize_png(
    png: Path,
    paddle: str,
    level: int,
    timeout: float,
    runner,
    warn,
) -> list[TextBox]:
    detection, recognition = _LEVEL_MODELS[level]
    save_dir = png.with_name(f"{png.stem}-ocr")
    save_dir.mkdir()
    try:
        from pdf2context.pipeline import execute

        stdout = execute(
            [
                paddle,
                "ocr",
                "-i",
                str(png),
                "--ocr_version",
                "PP-OCRv6",
                "--text_detection_model_name",
                detection,
                "--text_recognition_model_name",
                recognition,
                "--use_doc_orientation_classify",
                "False",
                "--use_doc_unwarping",
                "False",
                "--use_textline_orientation",
                "False",
                "--save_path",
                str(save_dir),
            ],
            timeout=timeout,
            runner=runner,
            warn=warn,
        )
        return _read_saved_result(save_dir, stdout)
    finally:
        shutil.rmtree(save_dir, ignore_errors=True)


def _read_saved_result(save_dir: Path, stdout: str) -> list[TextBox]:
    files = sorted(save_dir.rglob("*.json"))
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if _find_recognition(payload) is not None:
            return parse_recognition_json(payload)
    stdout = (stdout or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None
        if payload is not None and _find_recognition(payload) is not None:
            return parse_recognition_json(payload)
    _failure("paddle_result", detail=save_dir.name)


def _stamp(
    pdf: pdfium.PdfDocument,
    font_path: Path,
    recognized: Sequence[tuple[int, list[TextBox]]],
    characters: str,
) -> None:
    font_bytes = _subset_font(font_path, characters)
    buffer = (ctypes.c_ubyte * len(font_bytes)).from_buffer_copy(font_bytes)
    font = raw.FPDFText_LoadFont(
        pdf.raw, buffer, len(font_bytes), raw.FPDF_FONT_TRUETYPE, True
    )
    if not font:
        _failure("font_embed_failed", path=font_path)
    try:
        for index, boxes in recognized:
            page = pdf[index]
            _width, height = page.get_size()
            for box in boxes:
                _place_box(pdf, page, font, box, height)
            page.gen_content()
    finally:
        raw.FPDFFont_Close(font)


def _place_box(pdf, page, font, box: TextBox, page_height: float) -> None:
    font_size = max((box.y1 - box.y0) / RECOGNITION_SCALE, 1)
    obj = raw.FPDFPageObj_CreateTextObj(pdf.raw, font, font_size)
    if not obj:
        _failure("font_embed_failed", path="")
    wide = (ctypes.c_ushort * (len(box.text) + 1))(*(ord(char) for char in box.text), 0)
    if not raw.FPDFText_SetText(obj, wide):
        _failure("font_embed_failed", path=box.text)
    raw.FPDFPageObj_Transform(
        obj,
        1,
        0,
        0,
        1,
        box.x0 / RECOGNITION_SCALE,
        page_height - (box.y1 / RECOGNITION_SCALE),
    )
    raw.FPDFTextObj_SetTextRenderMode(obj, raw.FPDF_TEXTRENDERMODE_INVISIBLE)
    if not raw.FPDFPage_InsertObject(page.raw, obj):
        _failure("font_embed_failed", path=box.text)


def _drop_text(page) -> None:
    objects = list(page.get_objects(filter=(raw.FPDF_PAGEOBJ_TEXT,)))
    for obj in objects:
        page.remove_obj(obj)
    if objects:
        page.gen_content()


def _subset_font(path: Path, text: str) -> bytes:
    font = TTFont(path, fontNumber=_face_index(path))
    try:
        if "fvar" in font:
            font = instantiateVariableFont(font, {"wght": 400}, inplace=False)
        subsetter = Subsetter()
        subsetter.populate(text=text)
        subsetter.subset(font)
        output = io.BytesIO()
        font.save(output)
        return output.getvalue()
    except Exception as exc:
        from pdf2context.pipeline import Pdf2ContextError

        raise Pdf2ContextError(say("font_embed_failed", path=path)) from exc


def _face_index(path: Path) -> int:
    if path.suffix.lower() not in {".ttc", ".otc"}:
        return 0
    collection = TTFont(path, fontNumber=0, lazy=True)
    count = getattr(collection.reader, "numFonts", 1)
    collection.close()
    for index in range(count):
        face = TTFont(path, fontNumber=index, lazy=True)
        try:
            strings = []
            for record in face["name"].names:
                try:
                    strings.append(record.toUnicode())
                except Exception:
                    continue
            name = " ".join(strings).lower()
        finally:
            face.close()
        if "jp" in name or "japanese" in name:
            return index
    return 0


def _page_needs_ocr(text: str, mode: str) -> bool:
    if mode == "force":
        return True
    return not any(not char.isspace() for char in text)


def _is_noto_sans_cjk(path: Path) -> bool:
    if path.suffix.lower() not in {".otf", ".ttf", ".ttc", ".otc"}:
        return False
    compact = path.name.lower().replace("-", "").replace("_", "").replace(" ", "")
    return "notosanscjk" in compact


def _font_rank(path: Path) -> tuple:
    name = path.name.lower()
    japanese = "jp" in name or "japanese" in name
    regular = "regular" in name
    variable = "[" in name or "-vf" in name
    if japanese and regular:
        group = 0
    elif regular:
        group = 1
    else:
        group = 2
    return (group, 1 if variable else 0, str(path).lower())


def _find_recognition(payload: object) -> Optional[tuple[list, list]]:
    if isinstance(payload, dict):
        if "rec_texts" in payload and "rec_boxes" in payload:
            return list(payload["rec_texts"]), list(payload["rec_boxes"])
        for value in payload.values():
            found = _find_recognition(value)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_recognition(item)
            if found is not None:
                return found
    return None


def ocr_language_codes(ocr_lang: str) -> list[str]:
    return [code for code in ocr_lang.replace(",", "+").split("+") if code]


def level_languages_allowed(ocr_lang: str) -> bool:
    codes = ocr_language_codes(ocr_lang)
    return bool(codes) and set(codes) <= {"jpn", "eng"}
