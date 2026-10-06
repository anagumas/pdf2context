[English](README.md) | [日本語](README.ja.md)

# pdf2context

Turn multiple PDFs into one corpus. What you hand to an AI is the PDF and the Markdown.

Pass `-o` an output path without an extension. For `/hoge/context/merged`, the same directory gets these three files:

- `/hoge/context/merged.pdf` — the merged PDF. It is the authoritative copy of how the pages look.
- `/hoge/context/merged.md` — text with a source citation on every page.
- `/hoge/context/merged.json` — a record for reusing sources from the previous run. It stores the source, the SHA-256, and the page text.

Each page heading carries both the page number in the merged file and the page number in the original file. The body is wrapped in a code fence.

```text
### contract.pdf — source p.4 — merged p.16
```

## Requirements

Merging PDFs and extracting text requires these commands:

```bash
brew install qpdf poppler
```

OCR is performed by [OCRmyPDF](https://ocrmypdf.readthedocs.io/). `uv run` installs that package. Pages are rasterized with `pypdfium2`, which is installed alongside it, so Ghostscript is not required.

The Tesseract binary is required only when you use OCR. `brew install tesseract` includes the English trained data. The full language pack `tesseract-lang` is not required. To read Japanese, add only `jpn.traineddata`.

```bash
brew install tesseract
curl -L "https://github.com/tesseract-ocr/tessdata/raw/main/jpn.traineddata" \
  -o "$(brew --prefix)/share/tessdata/jpn.traineddata"
```

## Usage

Run this from the repository root. `uv run` installs the package into a virtual environment and starts it as the `pdf2context` command.

```bash
uv run pdf2context '/hoge/pdf_a/*.pdf' -o /hoge/context/merged
uv run pdf2context '/hoge/pdf_a/*.pdf' -o /hoge/context/pdf_a
uv run pdf2context docs/ -o output/merged
uv run pdf2context --ocr auto --ocr-lang jpn+eng shots/*.pdf -o output/merged
uv run pdf2context --ocr force --update replace shots/*.pdf -o output/merged
uv run pdf2context --dry-run --prune shots/*.pdf -o output/merged
uv run pdf2context --lang ja docs/ -o output/merged
```

For `/hoge/context/pdf_a`, the file names are `pdf_a.pdf`, `pdf_a.md`, and `pdf_a.json`. If the path ends in `.pdf`, `.md`, or `.json`, that extension is stripped and the same rule applies.

A directory argument merges the PDFs directly inside it, in code-point order of the file names. Globs keep the order of the arguments; matched files are ordered by path name. Recursive globs such as `**/*.pdf` work. `2.pdf` sorts after `10.pdf`. To fix the order, zero-pad names such as `01_`, or pass the files explicitly as arguments.

If the same source name appears more than once with the same bytes, later copies are dropped. If several inputs share a source name but differ in bytes, the run errors. The `.pdf`, `.md`, and `.json` about to be written are excluded from the input.

Reruns follow `--update`. The default, `changed`, reuses a source whose source name, bytes, and OCR settings match the previous run, and rebuilds only sources whose bytes changed. `replace` rebuilds the sources passed this time. `keep` leaves an existing source name on its previous pages even when the bytes changed. Source names absent from the input stay. `--prune` drops them. When the result matches the previous run, files are not rewritten, except under `replace`.

`--lang` is `en` or `ja`. It selects the language of errors, help, and progress logs. The first run defaults to `en`. A later run, when `--lang` is omitted, uses `options.language` from the previous JSON. Passing `--lang` with a different value rewrites only that JSON field. The PDF and the Markdown stay as they are. `--dry-run` prints `language: ja -> en` when that field would change. Dry-run status names stay in English: `added`, `replaced`, `reused`, `kept`, `retained`, `pruned`, and `same-content`.

The Markdown contains an English `## Notice` section. It does not follow `--lang`.

A previous JSON without `options.language`, or with a value other than `en` or `ja`, is an error. The message names the line where `"language": "en"` or `"language": "ja"` goes, inside `options`. `--update replace` and `--dry-run` stop as well.

`--dry-run` writes no files. It prints the outcome for each source name, then the pairs that have different names and the same bytes. That same-content list is the set before `--prune` is applied. The command still exits successfully when such pairs exist. A real run does not stop because of them. `changed` and `keep` with no previous JSON, and an empty input, fail the same way as a real run.

Symbolic links and directories are not replaced. During a run, `.{name}.pdf2context.lock` is placed at the output location, and a concurrent run is refused. If replacement fails, the previous output is restored.

Each external command is limited to `--timeout` seconds. The default is 600.

## OCR

`--ocr` is `off`, `auto`, or `force`. The default is `off`. The default language is `jpn+eng`.

OCRmyPDF writes the recognized characters back into the PDF as an invisible text layer. The page looks the same, while search, copy, and a later `pdftotext` can read those characters. Skew is not corrected. The output is not converted to PDF/A. If the page count changes after OCR, the run stops.

- `auto` leaves any page from which at least one character can be extracted as it is, and adds a text layer only to pages with no characters. A page that is only a page number, or an image with a single heading line, is left out entirely.
- `force` discards existing text and OCRs every page again. Use it for garbled text, or for an image whose only text is a caption. Page images are regenerated.

## Text extraction

Each page is extracted with `pdftotext -f N -l N -nopgbrk -layout`. The whole file is not split on form-feed characters. Pass `--no-layout` to drop `-layout`.

The JSON is the record of the corpus. When the previous JSON is missing and only the PDF or the Markdown remains, `changed` and `keep` stop. To rebuild, pass `--update replace`.

## What this tool does not produce

This tool does not restore tables or headings into Markdown structure. OCR recovers characters.

Encrypted PDFs are rejected. Remove the password before passing the file.

## Development

```bash
uv run python -m unittest discover -s tests -v
```

## License

Apache License 2.0
