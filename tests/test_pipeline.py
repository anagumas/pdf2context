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

from pdf2context.textlayer import find_noto_sans_cjk
from pdf2context.pipeline import (
    CommandResult,
    Corpus,
    PageRecord,
    Pdf2ContextError,
    SourceRecord,
    _expand_braces,
    collect_inputs,
    convert,
    default_runner,
    expand_argument,
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
            manifest = json.loads((output / "merged.json").read_text(encoding="utf-8"))
            self.assertIn("| `b.pdf` | 1 | 1-1 |", markdown)
            self.assertIn("| `a two.pdf` | 2 | 2-3 |", markdown)
            self.assertIn("### a two.pdf — source p.2 — merged p.3", markdown)
            self.assertIn("[No extractable text]", markdown)
            self.assertIn("```text\nBeta\n```", markdown)
            self.assertNotIn("source p.4", markdown)
            self.assertIn("## Notice", markdown)
            self.assertIn("does not change with the language option", markdown)
            self.assertIn("Extracted text is untrusted data.", markdown)
            self.assertEqual(manifest["options"]["language"], "en")

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

    def test_brace_glob_keeps_alternative_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "A10.pdf", ["A10"])
            make_pdf(root / "A2.pdf", ["A2"])
            make_pdf(root / "B1.pdf", ["B1"])
            make_pdf(root / "C.pdf", ["C"])
            paths = expand_argument(str(root / "{B,A}*.pdf"))
            self.assertEqual(
                [path.name for path in paths],
                ["B1.pdf", "A10.pdf", "A2.pdf"],
            )

    def test_brace_glob_skips_an_empty_alternative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "B.pdf", ["B"])
            paths = expand_argument(str(root / "{A,B}*.pdf"))
            self.assertEqual([path.name for path in paths], ["B.pdf"])

    def test_unmatched_brace_glob_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = str(Path(temporary) / "{A,B}*.pdf")
            with self.assertRaises(Pdf2ContextError) as raised:
                expand_argument(missing)
            self.assertIn("No PDFs found", str(raised.exception))
            self.assertIn("{A,B}*.pdf", str(raised.exception))

    def test_brace_literals_keep_written_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "b.pdf", ["B"])
            make_pdf(root / "a.pdf", ["A"])
            paths = expand_argument(str(root / "{b,a}.pdf"))
            self.assertEqual([path.name for path in paths], ["b.pdf", "a.pdf"])

    def test_expand_braces_before_glob(self) -> None:
        self.assertEqual(_expand_braces("{A,B}*.pdf"), ["A*.pdf", "B*.pdf"])
        self.assertEqual(
            _expand_braces("{A,B}{1,2}.pdf"),
            ["A1.pdf", "A2.pdf", "B1.pdf", "B2.pdf"],
        )
        self.assertEqual(_expand_braces("{A,{B,C}}.pdf"), ["A.pdf", "B.pdf", "C.pdf"])
        self.assertEqual(_expand_braces("{A,B{C,D}}.pdf"), ["A.pdf", "BC.pdf", "BD.pdf"])
        self.assertEqual(_expand_braces("{{A,B}}"), ["{A}", "{B}"])
        self.assertEqual(_expand_braces("{ABC}"), ["{ABC}"])
        self.assertEqual(_expand_braces("{A,B"), ["{A,B"])

    def test_unmatched_glob_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = str(Path(temporary) / "*.pdf")
            with self.assertRaises(Pdf2ContextError) as raised:
                collect_inputs([missing], [])
            self.assertIn("No PDFs found", str(raised.exception))

    def test_output_pdf_is_not_used_as_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "note.pdf", ["Note"])
            make_pdf(root / "merged.pdf", ["Old merge"])
            corpus = convert(
                [str(root)],
                root / "merged",
                update="replace",
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

    def test_identical_second_run_leaves_the_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            make_pdf(pdf, ["A"])
            output = root / "output"
            recorded = []

            def runner(args, timeout):
                recorded.append(list(args))
                return default_runner(args, timeout)

            _convert([str(pdf)], output, runner=runner)
            before = (output / "merged.json").read_bytes()
            recorded.clear()
            _convert([str(pdf)], output, runner=runner)
            self.assertEqual(before, (output / "merged.json").read_bytes())
            self.assertFalse(any(Path(call[0]).name == "pdftotext" for call in recorded))

    def test_symlink_output_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            other = root / "other.pdf"
            make_pdf(pdf, ["A"])
            make_pdf(other, ["B"])
            output = root / "output"
            _convert([str(pdf)], output)
            (output / "merged.pdf").unlink()
            (output / "merged.pdf").symlink_to(other)
            make_pdf(pdf, ["Changed"])
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert([str(pdf)], output)
            self.assertIn("regular file", str(raised.exception))

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
                self.assertIn("locked", str(raised.exception))
                self.assertTrue(lock.is_file())
            finally:
                lock.unlink()

    def test_same_basename_with_different_bytes_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "one" / "a.pdf", ["One"])
            make_pdf(root / "two" / "a.pdf", ["Two"])
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert(
                    [str(root / "one" / "a.pdf"), str(root / "two" / "a.pdf")],
                    root / "output",
                )
            self.assertIn("Same source name", str(raised.exception))

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

    def test_missing_json_stops_an_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            make_pdf(pdf, ["A"])
            output = root / "output"
            _convert([str(pdf)], output)
            (output / "merged.json").unlink()
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert([str(pdf)], output)
            self.assertIn("JSON", str(raised.exception))
            _convert([str(pdf)], output, update="replace")
            self.assertTrue((output / "merged.json").is_file())

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
            self.assertIn("Page count", str(raised.exception))

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
            self.assertIn("password", str(raised.exception))


    def test_omitted_source_stays_and_new_names_append(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["A", "A2"])
            make_pdf(root / "b.pdf", ["B"])
            output = root / "output"
            _convert([str(root / "a.pdf"), str(root / "b.pdf")], output)
            make_pdf(root / "e.pdf", ["E"])
            make_pdf(root / "c.pdf", ["C"])
            recorded = []

            def runner(args, timeout):
                recorded.append(list(args))
                return default_runner(args, timeout)

            corpus = _convert(
                [str(root / "e.pdf"), str(root / "a.pdf"), str(root / "c.pdf")],
                output,
                runner=runner,
            )
            self.assertEqual(
                [source.source_file for source in corpus.sources],
                ["a.pdf", "b.pdf", "e.pdf", "c.pdf"],
            )
            self.assertEqual(
                [page.text for page in corpus.pages],
                ["A", "A2", "B", "E", "C"],
            )
            text_calls = [call for call in recorded if Path(call[0]).name == "pdftotext"]
            self.assertEqual(len(text_calls), 2)

    def test_prune_drops_omitted_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["A"])
            make_pdf(root / "b.pdf", ["B"])
            output = root / "output"
            _convert([str(root / "a.pdf"), str(root / "b.pdf")], output)
            corpus = _convert([str(root / "a.pdf")], output, prune=True)
            self.assertEqual([source.source_file for source in corpus.sources], ["a.pdf"])
            self.assertNotIn("B", (output / "merged.md").read_text(encoding="utf-8"))

    def test_keep_retains_previous_pages_when_bytes_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            make_pdf(pdf, ["A"])
            output = root / "output"
            _convert([str(pdf)], output)
            make_pdf(pdf, ["AX"])
            corpus = _convert([str(pdf)], output, update="keep")
            self.assertEqual(corpus.pages[0].text, "A")
            self.assertNotIn("AX", (output / "merged.md").read_text(encoding="utf-8"))

    def test_changed_replaces_only_the_source_whose_bytes_differ(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            make_pdf(pdf, ["A"])
            make_pdf(root / "b.pdf", ["B"])
            output = root / "output"
            _convert([str(pdf), str(root / "b.pdf")], output)
            make_pdf(pdf, ["AX"])
            corpus = _convert([str(pdf)], output)
            self.assertEqual([page.text for page in corpus.pages], ["AX", "B"])
            self.assertEqual(corpus.pages[1].merged_page, 2)

    def test_same_bytes_under_another_name_are_kept_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "a.pdf"
            make_pdf(original, ["A"])
            output = root / "output"
            _convert([str(original)], output)
            renamed = root / "b-final.pdf"
            shutil.copyfile(original, renamed)
            lines: list[str] = []
            before = (output / "merged.json").read_bytes()
            _convert(
                [str(renamed)],
                output,
                dry_run=True,
                report=lines.append,
            )
            self.assertEqual(before, (output / "merged.json").read_bytes())
            self.assertIn("retained a.pdf", lines)
            self.assertIn("added b-final.pdf", lines)
            self.assertIn("same-content: a.pdf, b-final.pdf", lines)
            lines.clear()
            _convert(
                [str(renamed)],
                output,
                prune=True,
                dry_run=True,
                report=lines.append,
            )
            self.assertIn("pruned a.pdf", lines)
            self.assertIn("same-content: a.pdf, b-final.pdf", lines)
            corpus = _convert([str(renamed)], output)
            self.assertEqual(
                [source.source_file for source in corpus.sources],
                ["a.pdf", "b-final.pdf"],
            )

    def test_replace_rewrites_an_identical_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "a.pdf"
            make_pdf(pdf, ["A"])
            output = root / "output"
            _convert([str(pdf)], output)
            before = json.loads((output / "merged.json").read_text(encoding="utf-8"))["created_at"]
            _convert([str(pdf)], output, update="replace")
            after = json.loads((output / "merged.json").read_text(encoding="utf-8"))["created_at"]
            self.assertNotEqual(before, after)

    def test_dry_run_writes_nothing_on_the_first_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["A"])
            output = root / "output"
            lines: list[str] = []
            _convert([str(root / "a.pdf")], output, dry_run=True, report=lines.append)
            self.assertEqual(lines, ["added a.pdf"])
            self.assertFalse(output.exists())

    def test_source_over_the_max_leaves_the_previous_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Alpha"])
            output = root / "output"
            _convert([str(root / "a.pdf")], output)
            before_pdf = (output / "merged.pdf").read_bytes()
            before_json = (output / "merged.json").read_bytes()
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert([str(root / "a.pdf")], output, max_pdf_bytes=1)
            self.assertIn("maximum PDF size", str(raised.exception))
            self.assertEqual((output / "merged.pdf").read_bytes(), before_pdf)
            self.assertEqual((output / "merged.json").read_bytes(), before_json)

    def test_source_over_the_max_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Alpha"])
            output = root / "output"
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert([str(root / "a.pdf")], output, max_pdf_bytes=1, language="ja")
            self.assertIn("上限", str(raised.exception))
            self.assertFalse((output / "merged.pdf").exists())

    def test_sources_after_the_limit_are_left_out(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Alpha"])
            make_pdf(root / "b.pdf", [f"P{index}" for index in range(12)])
            make_pdf(root / "c.pdf", ["Gamma"])
            fitted = root / "fitted"
            _convert([str(root / "a.pdf")], fitted)
            limit = (fitted / "merged.pdf").stat().st_size
            output = root / "output"
            warnings: list[str] = []
            corpus = _convert(
                [str(root / "a.pdf"), str(root / "b.pdf"), str(root / "c.pdf")],
                output,
                max_pdf_bytes=limit,
                warn=warnings.append,
            )
            self.assertEqual(
                [source.source_file for source in corpus.sources],
                ["a.pdf"],
            )
            self.assertEqual(_page_count(output / "merged.pdf"), 1)
            self.assertIn("Alpha", _pdftotext(output / "merged.pdf"))
            markdown = (output / "merged.md").read_text(encoding="utf-8")
            self.assertIn("Alpha", markdown)
            self.assertNotIn("b.pdf", markdown)
            self.assertNotIn("Gamma", markdown)
            manifest = json.loads((output / "merged.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [source["source_file"] for source in manifest["sources"]],
                ["a.pdf"],
            )
            self.assertNotIn("in_pdf", manifest["sources"][0])
            self.assertEqual(manifest["options"]["max_pdf_bytes"], limit)
            self.assertTrue(any("b.pdf" in message for message in warnings))
            self.assertTrue(any("c.pdf" in message for message in warnings))

    def test_dropping_the_cap_adds_the_omitted_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Alpha"])
            make_pdf(root / "b.pdf", [f"P{index}" for index in range(12)])
            fitted = root / "fitted"
            _convert([str(root / "a.pdf")], fitted)
            limit = (fitted / "merged.pdf").stat().st_size
            output = root / "output"
            _convert(
                [str(root / "a.pdf"), str(root / "b.pdf")],
                output,
                max_pdf_bytes=limit,
            )
            self.assertEqual(_page_count(output / "merged.pdf"), 1)
            corpus = _convert([str(root / "a.pdf"), str(root / "b.pdf")], output)
            self.assertEqual(
                [source.source_file for source in corpus.sources],
                ["a.pdf", "b.pdf"],
            )
            manifest = json.loads((output / "merged.json").read_text(encoding="utf-8"))
            self.assertIsNone(manifest["options"]["max_pdf_bytes"])
            self.assertIn("P0", _pdftotext(output / "merged.pdf"))

    def test_same_cap_leaves_the_corpus_and_warns_again(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Alpha"])
            make_pdf(root / "b.pdf", [f"P{index}" for index in range(12)])
            fitted = root / "fitted"
            _convert([str(root / "a.pdf")], fitted)
            limit = (fitted / "merged.pdf").stat().st_size
            output = root / "output"
            _convert(
                [str(root / "a.pdf"), str(root / "b.pdf")],
                output,
                max_pdf_bytes=limit,
            )
            before = (output / "merged.json").read_bytes()
            warnings: list[str] = []
            _convert(
                [str(root / "a.pdf"), str(root / "b.pdf")],
                output,
                max_pdf_bytes=limit,
                warn=warnings.append,
            )
            self.assertEqual((output / "merged.json").read_bytes(), before)
            self.assertTrue(any("b.pdf" in message for message in warnings))

    def test_a_new_source_stays_out_when_earlier_sources_fill_the_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Alpha"])
            make_pdf(root / "b.pdf", ["Beta"])
            make_pdf(root / "c.pdf", [f"P{index}" for index in range(12)])
            fitted = root / "fitted"
            _convert([str(root / "a.pdf"), str(root / "b.pdf")], fitted)
            limit = (fitted / "merged.pdf").stat().st_size
            output = root / "output"
            _convert([str(root / "a.pdf"), str(root / "b.pdf")], output)
            warnings: list[str] = []
            corpus = _convert(
                [str(root / "a.pdf"), str(root / "b.pdf"), str(root / "c.pdf")],
                output,
                max_pdf_bytes=limit,
                warn=warnings.append,
            )
            names = [source.source_file for source in corpus.sources]
            self.assertIn("a.pdf", names)
            self.assertNotIn("c.pdf", names)
            self.assertTrue(any("c.pdf" in message for message in warnings))

    def test_dry_run_reports_capped_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Alpha"])
            make_pdf(root / "b.pdf", [f"P{index}" for index in range(12)])
            make_pdf(root / "c.pdf", ["Gamma"])
            fitted = root / "fitted"
            _convert([str(root / "a.pdf")], fitted)
            limit = (fitted / "merged.pdf").stat().st_size
            output = root / "output"
            lines: list[str] = []
            _convert(
                [str(root / "a.pdf"), str(root / "b.pdf"), str(root / "c.pdf")],
                output,
                max_pdf_bytes=limit,
                dry_run=True,
                report=lines.append,
            )
            self.assertEqual(lines, ["added a.pdf", "capped b.pdf", "capped c.pdf"])
            self.assertFalse(output.exists())

    def test_dry_run_over_the_max_reports_then_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Alpha"])
            output = root / "output"
            lines: list[str] = []
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert(
                    [str(root / "a.pdf")],
                    output,
                    max_pdf_bytes=1,
                    dry_run=True,
                    report=lines.append,
                )
            self.assertEqual(lines, ["capped a.pdf"])
            self.assertIn("maximum PDF size", str(raised.exception))
            self.assertFalse(output.exists())


class LanguageTest(unittest.TestCase):
    def test_notice_stays_english_when_lang_is_ja(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["A"])
            output = root / "output"
            logs: list[str] = []
            _convert([str(root / "a.pdf")], output, language="ja", log=logs.append)
            markdown = (output / "merged.md").read_text(encoding="utf-8")
            self.assertIn("## Notice", markdown)
            self.assertIn("This section is written in English.", markdown)
            self.assertNotIn("抽出した本文", markdown)
            self.assertEqual(
                json.loads((output / "merged.json").read_text(encoding="utf-8"))["options"]["language"],
                "ja",
            )
            self.assertTrue(any("完了" in line for line in logs))

    def test_omitted_lang_keeps_the_stored_language(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "one" / "a.pdf", ["One"])
            output = root / "output"
            _convert([str(root / "one" / "a.pdf")], output, language="ja")
            make_pdf(root / "two" / "a.pdf", ["Two"])
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert(
                    [str(root / "one" / "a.pdf"), str(root / "two" / "a.pdf")],
                    output,
                )
            self.assertIn("同じ出典名", str(raised.exception))
            self.assertEqual(
                json.loads((output / "merged.json").read_text(encoding="utf-8"))["options"]["language"],
                "ja",
            )

    def test_lang_change_rewrites_only_the_json_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["A"])
            output = root / "output"
            _convert([str(root / "a.pdf")], output, language="ja")
            pdf_before = (output / "merged.pdf").read_bytes()
            markdown_before = (output / "merged.md").read_bytes()
            json_before = json.loads((output / "merged.json").read_text(encoding="utf-8"))
            lines: list[str] = []
            _convert(
                [str(root / "a.pdf")],
                output,
                language="en",
                dry_run=True,
                report=lines.append,
            )
            self.assertIn("language: ja -> en", lines)
            self.assertEqual(
                json.loads((output / "merged.json").read_text(encoding="utf-8"))["options"]["language"],
                "ja",
            )
            _convert([str(root / "a.pdf")], output, language="en")
            self.assertEqual((output / "merged.pdf").read_bytes(), pdf_before)
            self.assertEqual((output / "merged.md").read_bytes(), markdown_before)
            after = json.loads((output / "merged.json").read_text(encoding="utf-8"))
            json_before["options"]["language"] = "en"
            self.assertEqual(after, json_before)

    def test_missing_language_names_the_line_to_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["A"])
            output = root / "output"
            _convert([str(root / "a.pdf")], output)
            path = output / "merged.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            del data["options"]["language"]
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            line = next(
                number
                for number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
                if '"options"' in text
            ) + 1
            with self.assertRaises(Pdf2ContextError) as dry_run:
                _convert([str(root / "a.pdf")], output, dry_run=True)
            message = str(dry_run.exception)
            self.assertIn(f"{path}:{line}:", message)
            self.assertIn('Add "language": "en" or "language": "ja" inside options.', message)
            with self.assertRaises(Pdf2ContextError) as replaced:
                _convert([str(root / "a.pdf")], output, update="replace")
            self.assertIn(f"{path}:{line}:", str(replaced.exception))

    def test_invalid_language_names_its_line(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["A"])
            output = root / "output"
            _convert([str(root / "a.pdf")], output, language="ja")
            path = output / "merged.json"
            text = path.read_text(encoding="utf-8").replace('"language": "ja"', '"language": "fr"', 1)
            path.write_text(text, encoding="utf-8")
            line = next(
                number
                for number, row in enumerate(text.splitlines(), start=1)
                if '"language"' in row
            )
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert([str(root / "a.pdf")], output, language="ja")
            self.assertIn(f"{path}:{line}:", str(raised.exception))
            self.assertIn("language は", str(raised.exception))


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
        self.assertIn("timed out", str(raised.exception))


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
            self.assertIn("directory", str(raised.exception))

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

    def test_dry_run_prints_the_plan_and_keeps_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Hello"])
            output = root / "out"
            first = subprocess.run(
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
            self.assertEqual(first.returncode, 0, first.stderr)
            preview = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pdf2context",
                    "--dry-run",
                    str(root / "a.pdf"),
                    "-o",
                    str(output / "merged"),
                ],
                cwd=ROOT,
                env={**_env(), "PYTHONPATH": str(SRC)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertIn("reused a.pdf", preview.stdout)
            self.assertNotIn("same-content:", preview.stdout)

    def test_help_follows_lang(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            english = subprocess.run(
                [sys.executable, "-m", "pdf2context", "--help"],
                cwd=temporary,
                env={**_env(), "PYTHONPATH": str(SRC)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(english.returncode, 0, english.stderr)
            self.assertIn("Output path without an extension", english.stdout)
            japanese = subprocess.run(
                [sys.executable, "-m", "pdf2context", "--lang", "ja", "--help"],
                cwd=temporary,
                env={**_env(), "PYTHONPATH": str(SRC)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(japanese.returncode, 0, japanese.stderr)
            self.assertIn("拡張子を除いた出力パス", japanese.stdout)

    def test_max_pdf_size_accepts_a_unit_and_rejects_garbage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Hello"])
            output = root / "out"
            command = [
                sys.executable,
                "-m",
                "pdf2context",
                str(root / "a.pdf"),
                "-o",
                str(output / "merged"),
            ]
            accepted = subprocess.run(
                [*command, "--max-pdf-size", "32MB"],
                cwd=ROOT,
                env={**_env(), "PYTHONPATH": str(SRC)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(_page_count(output / "merged.pdf"), 1)
            manifest = json.loads((output / "merged.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["options"]["max_pdf_bytes"], 32_000_000)
            rejected = subprocess.run(
                [*command, "--max-pdf-size", "nope"],
                cwd=ROOT,
                env={**_env(), "PYTHONPATH": str(SRC)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("32MB", rejected.stderr)
            japanese = subprocess.run(
                [*command, "--lang", "ja", "--max-pdf-size", "0"],
                cwd=ROOT,
                env={**_env(), "PYTHONPATH": str(SRC)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(japanese.returncode, 2)
            self.assertIn("サイズ", japanese.stderr)

    def test_quiet_still_warns_when_a_source_is_capped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Alpha"])
            make_pdf(root / "b.pdf", [f"P{index}" for index in range(12)])
            fitted = root / "fitted"
            measured = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pdf2context",
                    str(root / "a.pdf"),
                    "-o",
                    str(fitted / "merged"),
                ],
                cwd=ROOT,
                env={**_env(), "PYTHONPATH": str(SRC)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(measured.returncode, 0, measured.stderr)
            limit = (fitted / "merged.pdf").stat().st_size
            output = root / "out"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pdf2context",
                    "--quiet",
                    "--max-pdf-size",
                    str(limit),
                    str(root / "a.pdf"),
                    str(root / "b.pdf"),
                    "-o",
                    str(output / "merged"),
                ],
                cwd=ROOT,
                env={**_env(), "PYTHONPATH": str(SRC)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("b.pdf", completed.stderr)
            self.assertNotIn("Done:", completed.stderr)
            markdown = (output / "merged.md").read_text(encoding="utf-8")
            self.assertNotIn("b.pdf", markdown)


    def test_readmes_share_recognition_facts(self) -> None:
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        japanese = (ROOT / "README.ja.md").read_text(encoding="utf-8")
        for token in (
            'pip install "paddleocr>=3.7.0"',
            "brew install --cask font-noto-sans-cjk",
            "sudo apt install fonts-noto-cjk",
            "https://github.com/notofonts/noto-cjk/releases",
            "https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html",
            "NotoSansCJKjp-Regular.otf",
            "--ocr-level",
            "PP-OCRv6 small",
            "PP-OCRv6 medium",
            "300 dpi",
            "jpn+eng",
            "eng+jpn",
        ):
            self.assertIn(token, english)
            self.assertIn(token, japanese)

    def test_recognition_level_rejects_unknown_values_and_other_languages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", [None])
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert([str(root / "a.pdf")], root / "out", ocr_level=4)
            self.assertIn("1", str(raised.exception))
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert(
                    [str(root / "a.pdf")],
                    root / "out",
                    ocr="auto",
                    ocr_level=2,
                    ocr_lang="jpn+fra",
                    which=_paddle_which,
                    find_font=lambda: root / "missing.otf",
                )
            self.assertIn("jpn", str(raised.exception))

    def test_level_two_requires_paddle_and_noto_before_recognition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", [None])

            def which(name):
                if name == "paddleocr":
                    return None
                return shutil.which(name)

            with self.assertRaises(Pdf2ContextError) as raised:
                _convert(
                    [str(root / "a.pdf")],
                    root / "out",
                    ocr="auto",
                    ocr_level=2,
                    which=which,
                    find_font=lambda: None,
                )
            self.assertIn("paddleocr", str(raised.exception))
            with self.assertRaises(Pdf2ContextError) as raised:
                _convert(
                    [str(root / "a.pdf")],
                    root / "out",
                    ocr="auto",
                    ocr_level=2,
                    which=_paddle_which,
                    find_font=lambda: None,
                    dry_run=True,
                )
            self.assertIn("Noto Sans CJK", str(raised.exception))

    def test_off_ignores_recognition_level(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", ["Kept"])

            def which(name):
                if name == "paddleocr":
                    raise AssertionError(name)
                return shutil.which(name)

            _convert(
                [str(root / "a.pdf")],
                root / "out",
                ocr="off",
                ocr_level=3,
                which=which,
            )
            manifest = json.loads((root / "out" / "merged.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["options"]["ocr_level"], 1)

    def test_level_two_auto_skips_text_and_reads_blank_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            font = _test_font(root / "font.ttf")
            make_pdf(root / "text.pdf", ["Already"])
            make_pdf(root / "blank.pdf", [None])
            recorded = []
            text_corpus = _convert(
                [str(root / "text.pdf")],
                root / "text-out",
                ocr="auto",
                ocr_level=2,
                jobs=4,
                runner=_paddle_runner(recorded, ["ignored"]),
                which=_paddle_which,
                find_font=lambda: font,
            )
            self.assertEqual(recorded, [])
            self.assertEqual(text_corpus.pages[0].text, "Already")
            recorded.clear()
            blank = _convert(
                [str(root / "blank.pdf")],
                root / "blank-out",
                ocr="auto",
                ocr_level=2,
                ocr_lang="eng+jpn",
                jobs=4,
                runner=_paddle_runner(recorded, ["日Hi"]),
                which=_paddle_which,
                find_font=lambda: font,
            )
            self.assertEqual(blank.pages[0].text, "日Hi")
            self.assertEqual(len(recorded), 1)
            self.assertIn("PP-OCRv6_small_det", recorded[0])
            self.assertIn("PP-OCRv6_small_rec", recorded[0])
            self.assertIn("False", recorded[0])
            self.assertNotIn("4", recorded[0])
            self.assertNotIn("--deskew", recorded[0])
            manifest = json.loads((root / "blank-out" / "merged.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["options"]["ocr_level"], 2)

    def test_level_three_force_replaces_existing_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            font = _test_font(root / "font.ttf")
            make_pdf(root / "shot.pdf", ["Already"])
            recorded = []
            corpus = _convert(
                [str(root / "shot.pdf")],
                root / "out",
                ocr="force",
                ocr_level=3,
                runner=_paddle_runner(recorded, ["日Hi"]),
                which=_paddle_which,
                find_font=lambda: font,
            )
            self.assertEqual(corpus.pages[0].text, "日Hi")
            self.assertNotIn("Already", corpus.pages[0].text)
            self.assertIn("PP-OCRv6_medium_det", recorded[0])
            self.assertIn("PP-OCRv6_medium_rec", recorded[0])

    def test_paddle_failure_stops_and_keeps_the_previous_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            font = _test_font(root / "font.ttf")
            make_pdf(root / "a.pdf", ["Safe"])
            output = root / "out"
            _convert([str(root / "a.pdf")], output)
            make_pdf(root / "b.pdf", [None])

            def runner(args, timeout):
                if Path(args[0]).name == "paddleocr":
                    return CommandResult(1, "", "boom")
                return default_runner(args, timeout)

            with self.assertRaises(Pdf2ContextError):
                _convert(
                    [str(root / "a.pdf"), str(root / "b.pdf")],
                    output,
                    ocr="auto",
                    ocr_level=2,
                    runner=runner,
                    which=_paddle_which,
                    find_font=lambda: font,
                )
            self.assertIn("Safe", _pdftotext(output / "merged.pdf"))

    def test_missing_level_in_old_json_matches_level_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "a.pdf", [None])
            output = root / "out"
            recorded = []
            _convert(
                [str(root / "a.pdf")],
                output,
                ocr="auto",
                runner=_ocr_runner(recorded, lambda source, destination: shutil.copyfile(source, destination)),
                which=_which,
            )
            self.assertEqual(len(recorded), 1)
            manifest_path = output / "merged.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["options"]["ocr_level"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            recorded.clear()
            _convert(
                [str(root / "a.pdf")],
                output,
                ocr="auto",
                runner=_ocr_runner(recorded, lambda source, destination: shutil.copyfile(source, destination)),
                which=_which,
            )
            self.assertEqual(recorded, [])

    def test_changing_level_rebuilds_the_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            font = _test_font(root / "font.ttf")
            make_pdf(root / "a.pdf", [None])
            output = root / "out"
            _convert(
                [str(root / "a.pdf")],
                output,
                ocr="auto",
                runner=_ocr_runner([], lambda source, destination: shutil.copyfile(source, destination)),
                which=_which,
            )
            recorded = []
            corpus = _convert(
                [str(root / "a.pdf")],
                output,
                ocr="auto",
                ocr_level=2,
                runner=_paddle_runner(recorded, ["日Hi"]),
                which=_paddle_which,
                find_font=lambda: font,
            )
            self.assertEqual(len(recorded), 1)
            self.assertEqual(corpus.pages[0].text, "日Hi")

    def test_dry_run_level_two_does_not_run_paddle_even_with_a_size_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            font = _test_font(root / "font.ttf")
            make_pdf(root / "a.pdf", [None])
            recorded = []
            _convert(
                [str(root / "a.pdf")],
                root / "out",
                ocr="auto",
                ocr_level=2,
                dry_run=True,
                max_pdf_bytes=10_000_000,
                runner=_paddle_runner(recorded, ["日Hi"]),
                which=_paddle_which,
                find_font=lambda: font,
                report=lambda _message: None,
            )
            self.assertEqual(recorded, [])

    def test_noto_search_prefers_japanese_regular(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Hiragino.ttc").write_bytes(b"no")
            (root / "NotoSansJP-Regular.otf").write_bytes(b"no")
            (root / "NotoSansCJK-Bold.otf").write_bytes(b"no")
            chosen = root / "NotoSansCJKjp-Regular.otf"
            chosen.write_bytes(b"yes")
            self.assertEqual(find_noto_sans_cjk([root]), chosen)


def _convert(inputs, output, **kwargs):
    kwargs.setdefault("log", lambda _message: None)
    kwargs.setdefault("warn", lambda _message: None)
    return convert(inputs, Path(output) / "merged", **kwargs)


def _which(name):
    if name == "ocrmypdf":
        return "/usr/bin/ocrmypdf"
    return shutil.which(name)


def _test_font(path: Path) -> Path:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((400, 0))
    pen.lineTo((400, 600))
    pen.lineTo((50, 600))
    pen.closePath()
    glyph = pen.glyph()
    order = [".notdef", "H", "i", "uni65E5"]
    glyphs = {name: glyph for name in order}
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({ord("H"): "H", ord("i"): "i", 0x65E5: "uni65E5"})
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 50) for name in glyphs})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "TestOCR", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    builder.save(path)
    return path


def _paddle_which(name):
    if name == "paddleocr":
        return "/usr/bin/paddleocr"
    return shutil.which(name)


def _paddle_runner(recorded, texts):
    def runner(args, timeout):
        command = list(args)
        if Path(command[0]).name == "paddleocr":
            recorded.append(command)
            save = Path(command[command.index("--save_path") + 1])
            save.mkdir(parents=True, exist_ok=True)
            (save / "page_res.json").write_text(
                json.dumps(
                    {
                        "rec_texts": texts,
                        "rec_boxes": [[10, 20, 200, 80] for _text in texts],
                    }
                ),
                encoding="utf-8",
            )
            return CommandResult(0, "", "")
        return default_runner(command, timeout)

    return runner


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
