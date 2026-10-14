from __future__ import annotations

import argparse
import math
import re
import sys

from pdf2context import __version__
from pdf2context.messages import CATALOG, LANGUAGE, say
from pdf2context.pipeline import Pdf2ContextError, convert, message_language


def recognition_level(value: str) -> int:
    if value not in {"1", "2", "3"}:
        raise argparse.ArgumentTypeError(say("ocr_level"))
    return int(value)


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(say("expected_positive_int")) from exc
    if number <= 0:
        raise argparse.ArgumentTypeError(say("expected_positive_int"))
    return number


_PDF_SIZE_UNITS = {
    "": 1,
    "b": 1,
    "k": 1000,
    "kb": 1000,
    "ki": 1024,
    "kib": 1024,
    "m": 1_000_000,
    "mb": 1_000_000,
    "mi": 1024**2,
    "mib": 1024**2,
    "g": 1_000_000_000,
    "gb": 1_000_000_000,
    "gi": 1024**3,
    "gib": 1024**3,
}


def pdf_size(value: str) -> int:
    match = re.fullmatch(r"(\d+)\s*([a-z]*)", value.strip().lower())
    if match is None:
        raise argparse.ArgumentTypeError(say("expected_pdf_size"))
    number = int(match.group(1))
    unit = match.group(2)
    if number <= 0 or unit not in _PDF_SIZE_UNITS:
        raise argparse.ArgumentTypeError(say("expected_pdf_size"))
    size = number * _PDF_SIZE_UNITS[unit]
    if size <= 0:
        raise argparse.ArgumentTypeError(say("expected_pdf_size"))
    return size


def positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(say("expected_positive_number")) from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError(say("expected_positive_number"))
    return number


def build_parser(language: str) -> argparse.ArgumentParser:
    text = CATALOG[language]
    parser = argparse.ArgumentParser(
        prog="pdf2context",
        description=text["description"],
    )
    parser.add_argument("inputs", nargs="+", help=text["help_inputs"])
    parser.add_argument("-o", "--output", default="merged", help=text["help_output"])
    parser.add_argument(
        "--ocr",
        choices=["off", "auto", "force"],
        default="off",
        help=text["help_ocr"],
    )
    parser.add_argument("--ocr-lang", default="jpn+eng", help=text["help_ocr_lang"])
    parser.add_argument(
        "--ocr-level",
        type=recognition_level,
        default=1,
        help=text["help_ocr_level"],
    )
    parser.add_argument("--jobs", type=positive_int, default=1, help=text["help_jobs"])
    parser.add_argument(
        "--timeout",
        type=positive_float,
        default=600,
        help=text["help_timeout"],
    )
    parser.add_argument(
        "--max-pdf-size",
        type=pdf_size,
        default=None,
        help=text["help_max_pdf_size"],
    )
    parser.add_argument("--no-layout", action="store_true", help=text["help_no_layout"])
    parser.add_argument(
        "--update",
        choices=["changed", "replace", "keep"],
        default="changed",
        help=text["help_update"],
    )
    parser.add_argument("--prune", action="store_true", help=text["help_prune"])
    parser.add_argument("--dry-run", action="store_true", help=text["help_dry_run"])
    parser.add_argument("--quiet", action="store_true", help=text["help_quiet"])
    parser.add_argument(
        "--lang",
        choices=["en", "ja"],
        default=None,
        help=text["help_lang"],
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    explicit, output = _preview(argv)
    try:
        effective = message_language(output, explicit)
    except Pdf2ContextError as exc:
        print(exc, file=sys.stderr)
        return 1
    token = LANGUAGE.set(effective)
    try:
        args = build_parser(effective).parse_args(argv)
        log, warn = _handlers(args.quiet)
        try:
            convert(
                args.inputs,
                args.output,
                ocr=args.ocr,
                ocr_lang=args.ocr_lang,
                ocr_level=args.ocr_level,
                jobs=args.jobs,
                timeout=args.timeout,
                layout=not args.no_layout,
                update=args.update,
                prune=args.prune,
                dry_run=args.dry_run,
                language=args.lang,
                max_pdf_bytes=args.max_pdf_size,
                log=log,
                warn=warn,
            )
        except Pdf2ContextError as exc:
            print(exc, file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print(say("interrupted"), file=sys.stderr)
            return 130
        return 0
    finally:
        LANGUAGE.reset(token)


def _preview(argv: list[str]) -> tuple[str | None, str]:
    preview = argparse.ArgumentParser(add_help=False)
    preview.add_argument("--lang", default=None)
    preview.add_argument("-o", "--output", default="merged")
    known, _ = preview.parse_known_args(argv)
    explicit = known.lang if known.lang in {"en", "ja"} else None
    return explicit, known.output


def _handlers(quiet: bool) -> tuple:
    def log(message: str) -> None:
        if not quiet:
            print(message, file=sys.stderr)

    def warn(message: str) -> None:
        print(message, file=sys.stderr)

    return log, warn
