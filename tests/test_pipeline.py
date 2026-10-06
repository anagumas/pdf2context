from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pdf2context.pipeline import (
    CommandResult,
    Corpus,
    PageRecord,
    Pdf2ContextError,
    SourceRecord,
    collect_inputs,
    convert,
    default_runner,
    render_markdown,
    show_npages,
)
from pdfutil import make_pdf

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class ConvertTest(unittest.TestCase):
    def test_merges_pages_and_keeps_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "b.pdf", ["Beta"])
            make_pdf(root / "a two.pdf", ["Alpha", None])
            output = root / "output"
            recorded = []

            def runner(args, timeout):
                recorded.append(list(args))
                return default_runner(args, timeout)

            corpus = convert(
                [str(root / "b.pdf"), str(root / "a two.pdf")],
                output / "merged",
                runner=runner,
                log=lambda _message: None,
                warn=lambda _message: None,
            )

            self.assertEqual(
                [
                    (page.source_file, page.source_page, page.merged_page, page.text)
                    for page in corpus.pages
                ],
                [
                    ("b.pdf", 1, 1, "Beta"),
                    ("a two.pdf", 1, 2, "Alpha"),
                    ("a two.pdf", 2, 3, ""),
                ],
            )
            self.assertEqual(corpus.sources[0].merged_end, 1)
            self.assertEqual(
                (corpus.sources[1].merged_start, corpus.sources[1].merged_end),
                (2, 3),
            )

            markdown = (output / "merged.md").read_text(encoding="utf-8")
            self.assertIn("| `b.pdf` | 1 | 1-1 |", markdown)
            self.assertIn("| `a two.pdf` | 2 | 2-3 |", markdown)
            self.assertIn("### a two.pdf — source p.2 — merged p.3", markdown)
            self.assertIn("[No extractable text]", markdown)
            self.assertIn("```text\nBeta\n```", markdown)
            self.assertNotIn("source p.4", markdown)
            self.assertIn("信頼できないデータ", markdown)

            manifest = json.loads((output / "merged.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertFalse(manifest["pages"][2]["extractable"])
            self.assertEqual(manifest["pages"][2]["text"], "")
            self.assertEqual(manifest["pages"][0]["text_characters"], len("Beta"))
            self.assertEqual(len(manifest["sources"][0]["sha256"]), 64)
            self.assertIn("+00:00", manifest["created_at"])
            pdf_hash = hashlib.sha256((output / "merged.pdf").read_bytes()).hexdigest()
            self.assertEqual(manifest["outputs"]["merged.pdf"]["sha256"], pdf_hash)
            self.assertEqual(_page_count(output / "merged.pdf"), 3)
            merged_text = _pdftotext(output / "merged.pdf")
            self.assertIn("Beta", merged_text)
            self.assertIn("Alpha", merged_text)

            text_calls = [call for call in recorded if Path(call[0]).name == "pdftotext"]
            self.assertEqual(len(text_calls), 3)
            self.assertTrue(all("-nopgbrk" in call and "-f" in call and "-l" in call for call in text_calls))
            self.assertTrue(all("-layout" in call for call in text_calls))
            merges = [
                call
                for call in recorded
                if Path(call[0]).name == "qpdf" and "--pages" in call
            ]
            self.assertEqual(len(merges), 2)
            self.assertEqual(merges[0].count("1-z"), 1)
            self.assertEqual(merges[1].count("1-z"), 2)
            self.assertTrue(any(Path(call[0]).name == "qpdf" and "--check" in call for call in recorded))

    def test_empty_last_page_does_not_create_an_extra_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "last.pdf", ["Only", None])
            output = root / "output"
            corpus = _convert([str(root / "last.pdf")], output)
            self.assertEqual(len(corpus.pages), 2)
            self.assertEqual(corpus.pages[1].text, "")
            markdown = (output / "merged.md").read_text(encoding="utf-8")
            self.assertIn("source p.2", markdown)
            self.assertNotIn("source p.3", markdown)

    def test_directory_input_is_lexicographic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            make_pdf(source / "10.pdf", ["Ten"])
            make_pdf(source / "2.pdf", ["Two"])
            corpus = _convert([str(source)], root / "output")
            self.assertEqual([page.source_file for page in corpus.pages], ["10.pdf", "2.pdf"])

    def test_nested_glob(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Top"])
            make_pdf(root / "nested" / "b.pdf", ["Nested"])
            corpus = _convert([str(root / "**" / "*.pdf")], root / "output")
            self.assertEqual([page.text for page in corpus.pages], ["Top", "Nested"])

    def test_unmatched_glob_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = str(Path(temporary) / "*.pdf")
            with self.assertRaises(Pdf2ContextError) as raised:
                collect_inputs([missing], [])
            self.assertIn("PDF が見つかりません", str(raised.exception))

    def test_output_pdf_is_not_used_as_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "note.pdf", ["Note"])
            make_pdf(root / "merged.pdf", ["Old merge"])
            corpus = convert(
                [str(root)],
                root / "merged",
                overwrite=True,
                log=lambda _message: None,
                warn=lambda _message: None,
            )
            self.assertEqual([source.source_file for source in corpus.sources], ["note.pdf"])
            self.assertNotIn("Old merge", (root / "merged.md").read_text(encoding="utf-8"))

    def test_duplicate_input_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            make_pdf(pdf, ["A"])
            corpus = _convert([str(pdf), str(pdf)], root / "output")
            self.assertEqual([source.source_file for source in corpus.sources], ["a.pdf"])
            self.assertEqual(_page_count(root / "output" / "merged.pdf"), 1)

    def test_second_run_requires_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            make_pdf(pdf, ["A"])
            output = root / "output"
            _convert([str(pdf)], output)
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert([str(pdf)], output)
            self.assertIn("--overwrite", str(raised.exception))
            _convert([str(pdf)], output, overwrite=True)

    def test_symlink_output_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            other = root / "other.pdf"
            make_pdf(pdf, ["A"])
            make_pdf(other, ["B"])
            output = root / "output"
            output.mkdir()
            (output / "merged.pdf").symlink_to(other)
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert([str(pdf)], output, overwrite=True)
            self.assertIn("通常のファイル以外", str(raised.exception))

    def test_output_lock_is_respected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            make_pdf(pdf, ["A"])
            output = root / "output"
            output.mkdir()
            lock = output / ".merged.pdf2context.lock"
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            try:
                with self.assertRaises(Pdf2ContextError) as raised:
                    _convert([str(pdf)], output)
                self.assertIn("ロック", str(raised.exception))
                self.assertTrue(lock.is_file())
            finally:
                lock.unlink()

    def test_same_basename_is_qualified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "one" / "a.pdf", ["One"])
            make_pdf(root / "two" / "a.pdf", ["Two"])
            corpus = _convert(
                [str(root / "one" / "a.pdf"), str(root / "two" / "a.pdf")],
                root / "output",
            )
            self.assertEqual(
                [page.source_file for page in corpus.pages],
                ["one/a.pdf", "two/a.pdf"],
            )

    def test_no_layout_omits_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Hello"])
            recorded = []

            def runner(args, timeout):
                recorded.append(list(args))
                return default_runner(args, timeout)

            _convert([str(root / "a.pdf")], root / "output", layout=False, runner=runner)
            text_calls = [call for call in recorded if Path(call[0]).name == "pdftotext"]
            self.assertTrue(text_calls)
            self.assertTrue(all("-layout" not in call and "-nopgbrk" in call for call in text_calls))

    def test_no_manifest_omits_json_until_an_old_one_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            make_pdf(pdf, ["A"])
            output = root / "fresh"
            _convert([str(pdf)], output, manifest=False)
            self.assertTrue((output / "merged.md").is_file())
            self.assertFalse((output / "merged.json").exists())

            again = root / "again"
            _convert([str(pdf)], again)
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert([str(pdf)], again, manifest=False, overwrite=True)
            self.assertIn("merged.json", str(raised.exception))

    def test_missing_tesseract_language_stops_before_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "shot.pdf", [None])

            def runner(args, timeout):
                if Path(args[0]).name == "tesseract":
                    return CommandResult(0, "List of available languages (1):\neng\n", "")
                if Path(args[0]).name == "ocrmypdf":
                    raise AssertionError("OCR should not start without jpn")
                return default_runner(args, timeout)

            with self.assertRaises(Pdf2ContextError) as raised:
                _convert(
                    [str(root / "shot.pdf")],
                    root / "output",
                    ocr="auto",
                    ocr_lang="jpn+eng",
                    runner=runner,
                    which=_which,
                )
            self.assertIn("jpn", str(raised.exception))

    def test_ocr_auto_skips_text_without_deskew(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "shot.pdf", [None])
            recorded = []
            corpus = _convert(
                [str(root / "shot.pdf")],
                root / "output",
                ocr="auto",
                ocr_lang="jpn+eng",
                jobs=2,
                runner=_ocr_runner(recorded, lambda _source, destination: shutil.copyfile(_source, destination)),
                which=_which,
            )
            self.assertEqual(len(recorded), 1)
            self.assertIn("--skip-text", recorded[0])
            self.assertIn("--optimize", recorded[0])
            self.assertIn("jpn+eng", recorded[0])
            self.assertIn("2", recorded[0])
            self.assertNotIn("--deskew", recorded[0])
            self.assertNotIn("--force-ocr", recorded[0])
            self.assertEqual(corpus.pages[0].text, "")

    def test_ocr_force_uses_force_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "shot.pdf", ["Already"])
            recorded = []
            _convert(
                [str(root / "shot.pdf")],
                root / "output",
                ocr="force",
                runner=_ocr_runner(recorded, lambda source, destination: shutil.copyfile(source, destination)),
                which=_which,
            )
            self.assertIn("--force-ocr", recorded[0])
            self.assertNotIn("--skip-text", recorded[0])

    def test_ocr_that_changes_page_count_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "one.pdf", ["A"])
            make_pdf(root / "two.pdf", ["B", "C"])
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert(
                    [str(root / "one.pdf")],
                    root / "output",
                    ocr="auto",
                    runner=_ocr_runner(
                        [],
                        lambda _source, destination: shutil.copyfile(root / "two.pdf", destination),
                    ),
                    which=_which,
                )
            self.assertIn("ページ数", str(raised.exception))

    def test_encrypted_pdf_mentions_password(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plain = root / "plain.pdf"
            locked = root / "locked.pdf"
            make_pdf(plain, ["Secret"])
            completed = subprocess.run(
                ["qpdf", "--encrypt", "secret", "secret", "256", "--", str(plain), str(locked)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert([str(locked)], root / "output")
            self.assertIn("パスワード", str(raised.exception))


class CommandTest(unittest.TestCase):
    def test_qpdf_exit_3_is_a_warning(self) -> None:
        def runner(args, timeout):
            del args, timeout
            return CommandResult(3, "4\n", "warning: xref")

        self.assertEqual(
            show_npages(Path("a.pdf"), "qpdf", 5, runner, lambda _message: None),
            4,
        )

    def test_timeout(self) -> None:
        with self.assertRaises(Pdf2ContextError) as raised:
            default_runner(["sleep", "2"], 0.2)
        self.assertIn("タイムアウト", str(raised.exception))


class MarkdownTest(unittest.TestCase):
    def test_stem_selects_sibling_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            make_pdf(pdf, ["Hello"])
            stem = root / "context" / "pdf_a.pdf"
            convert([str(pdf)], stem, log=lambda _message: None, warn=lambda _message: None)
            directory = root / "context"
            self.assertTrue((directory / "pdf_a.pdf").is_file())
            self.assertTrue((directory / "pdf_a.md").is_file())
            self.assertTrue((directory / "pdf_a.json").is_file())
            self.assertFalse((directory / "pdf_a.pdf.pdf").exists())
            self.assertFalse((directory / "manifest.json").exists())
            self.assertIn("PDF: `pdf_a.pdf`", (directory / "pdf_a.md").read_text(encoding="utf-8"))

    def test_directory_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            make_pdf(pdf, ["A"])
            with self.assertRaises(Pdf2ContextError) as raised:
                convert(
                    [str(pdf)],
                    root,
                    log=lambda _message: None,
                    warn=lambda _message: None,
                )
            self.assertIn("ディレクトリ", str(raised.exception))

    def test_backticks_in_page_text_do_not_close_the_fence(self) -> None:
        corpus = Corpus(
            sources=[SourceRecord("a.pdf", 1, 1, 1)],
            pages=[PageRecord("a.pdf", 1, 1, "```")],
        )
        markdown = render_markdown(corpus)
        self.assertIn("````text\n```\n````", markdown)
        self.assertIn("### a.pdf — source p.1 — merged p.1", markdown)


class CliTest(unittest.TestCase):
    def test_cli_writes_three_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Hello"])
            output = root / "out"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pdf2context",
                    str(root / "a.pdf"),
                    "-o",
                    str(output / "merged"),
                ],
                cwd=ROOT,
                env={**_env(), "PYTHONPATH": str(SRC)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((output / "merged.pdf").is_file())
            self.assertTrue((output / "merged.md").is_file())
            self.assertTrue((output / "merged.json").is_file())
            self.assertIn("Hello", (output / "merged.md").read_text(encoding="utf-8"))
            self.assertFalse((output / ".merged.pdf2context.lock").exists())


def _convert(inputs, output, **kwargs):
    kwargs.setdefault("log", lambda _message: None)
    kwargs.setdefault("warn", lambda _message: None)
    return convert(inputs, Path(output) / "merged", **kwargs)


def _which(name):
    if name == "ocrmypdf":
        return "/usr/bin/ocrmypdf"
    return shutil.which(name)


def _ocr_runner(recorded, write_output):
    def runner(args, timeout):
        command = list(args)
        if Path(command[0]).name == "ocrmypdf":
            recorded.append(command)
            write_output(command[-2], command[-1])
            return CommandResult(0, "", "")
        return default_runner(command, timeout)

    return runner


def _page_count(path: Path) -> int:
    completed = subprocess.run(
        ["qpdf", "--show-npages", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(completed.stdout.strip())


def _pdftotext(path: Path) -> str:
    completed = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _env():
    return dict(os.environ)


if __name__ == "__main__":
    unittest.main()
