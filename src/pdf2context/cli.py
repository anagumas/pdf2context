from __future__ import annotations

import argparse
import math
import sys

from pdf2context import __version__
from pdf2context.pipeline import Pdf2ContextError, convert


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("正の整数を指定してください。") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("正の整数を指定してください。")
    return number


def positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("正の数を指定してください。") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("正の数を指定してください。")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf2context",
        description=(
            "複数の PDF を結合し、ページ単位の出典を持つ "
            ".pdf / .md / .json を作ります。"
        ),
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="PDF ファイル、PDF が入ったディレクトリ、またはグロブ",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="merged",
        help="拡張子を除いた出力パス（既定: merged）。例: /hoge/context/merged",
    )
    parser.add_argument(
        "--ocr",
        choices=["off", "auto", "force"],
        default="off",
        help="off: OCR しない。auto: 文字のないページだけ。force: 全ページを OCR し直す",
    )
    parser.add_argument(
        "--ocr-lang",
        default="jpn+eng",
        help="Tesseract の言語（既定: jpn+eng）",
    )
    parser.add_argument(
        "--jobs",
        type=positive_int,
        default=1,
        help="OCR の並列数（既定: 1）",
    )
    parser.add_argument(
        "--timeout",
        type=positive_float,
        default=600,
        help="外部コマンド 1 回のタイムアウト秒（既定: 600）",
    )
    parser.add_argument(
        "--no-layout",
        action="store_true",
        help="pdftotext の -layout を外す",
    )
    parser.add_argument(
        "--no-json",
        action="store_true",
        help="JSON を書かない。出典は Markdown に残る",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="既存の通常ファイルの出力を置き換える",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="完了メッセージを出さない",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log, warn = _handlers(args.quiet)
    try:
        convert(
            args.inputs,
            args.output,
            ocr=args.ocr,
            ocr_lang=args.ocr_lang,
            jobs=args.jobs,
            timeout=args.timeout,
            layout=not args.no_layout,
            manifest=not args.no_json,
            overwrite=args.overwrite,
            log=log,
            warn=warn,
        )
    except Pdf2ContextError as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("中断しました。", file=sys.stderr)
        return 130
    return 0


def _handlers(quiet: bool) -> tuple:
    def log(message: str) -> None:
        if not quiet:
            print(message, file=sys.stderr)

    def warn(message: str) -> None:
        print(message, file=sys.stderr)

    return log, warn
