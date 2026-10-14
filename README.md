[English](README.md) | [日本語](README.ja.md)

# pdf2context

Turn multiple PDFs into one corpus. What you hand to an AI is the PDF and the Markdown.

Pass `-o` an output path without an extension. For `/hoge/context/merged`, the same directory gets these three files:

- `/hoge/context/merged.pdf` — the merged PDF. It is the authoritative copy of how the pages look.
- `/hoge/context/merged.md` — text with a source citation on every page.
- `/hoge/context/merged.json` — a record for reusing sources from the previous run. It stores the source, the SHA-256, and the page text.

Hand `merged.pdf` and `merged.md` to the AI. `merged.json` is for this tool. Do not hand it to the AI.

Each page heading carries both the page number in the merged file and the page number in the original file. The body is wrapped in a code fence.

```text
### contract.pdf — source p.4 — merged p.16
```

## Requirements

Merging PDFs and extracting text requires these commands:

```bash
brew install qpdf poppler
```

Recognition level 1 uses [OCRmyPDF](https://ocrmypdf.readthedocs.io/). `uv run` installs that package. Pages are rasterized with `pypdfium2`, which is installed alongside it, so Ghostscript is not required.

Tesseract is required only for recognition level 1. `brew install tesseract` includes the English trained data. The full language pack `tesseract-lang` is not required. To read Japanese, add only `jpn.traineddata`.

```bash
brew install tesseract
curl -L "https://github.com/tesseract-ocr/tessdata/raw/main/jpn.traineddata" \
  -o "$(brew --prefix)/share/tessdata/jpn.traineddata"
```

Recognition levels 2 and 3 need [PaddleOCR](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html) 3.7.0 or newer, and [Noto Sans CJK](https://github.com/notofonts/noto-cjk). This package depends on `paddleocr>=3.7.0` and `paddlepaddle==3.2.0`. PaddleOCR, PaddlePaddle, and the PP-OCRv6 small and medium weights are Apache-2.0, the same license as this package. `uv sync` and `uv run` install them into the project environment, and `uv run` puts `paddleocr` on `PATH`. Wheels exist for Python 3.11, 3.12, and 3.13. Python 3.14 has none, so those dependencies are omitted there. The font is not bundled. Hiragino is not used.

Noto Sans CJK is under the SIL Open Font License 1.1. The glyphs written into the PDF may be embedded. Install the font locally.

macOS:

```bash
brew install --cask font-noto-sans-cjk
```

Debian and Ubuntu:

```bash
sudo apt install fonts-noto-cjk
```

Windows: install `NotoSansCJKjp-Regular.otf` from the [Noto CJK releases](https://github.com/notofonts/noto-cjk/releases) for the current user.

## Usage

Run this from the repository root. `uv run` installs the package into a virtual environment and starts it as the `pdf2context` command. `qpdf` and `pdftotext` still have to be on `PATH`, as described in Requirements. Without a clone, `uvx pdf2context` runs the package via PyPI.

```bash
uv run pdf2context '/hoge/pdf_a/*.pdf' -o /hoge/context/merged
uv run pdf2context '/hoge/pdf_a/*.pdf' -o /hoge/context/pdf_a
uv run pdf2context docs/ -o output/merged
uv run pdf2context --ocr auto --ocr-lang jpn+eng shots/*.pdf -o output/merged
uv run pdf2context --ocr force --update replace shots/*.pdf -o output/merged
uv run pdf2context --dry-run --prune shots/*.pdf -o output/merged
uv run pdf2context --lang ja docs/ -o output/merged
uv run pdf2context '{A,B}*.pdf' -o output/merged
uv run pdf2context --max-pdf-size 32MB docs/ -o output/merged
```

For `/hoge/context/pdf_a`, the file names are `pdf_a.pdf`, `pdf_a.md`, and `pdf_a.json`. If the path ends in `.pdf`, `.md`, or `.json`, that extension is stripped and the same rule applies.

A directory argument merges the PDFs directly inside it, in code-point order of the file names. Globs keep the order of the arguments; matched files are ordered by path name. Recursive globs such as `**/*.pdf` work. `2.pdf` sorts after `10.pdf`. To fix the order, zero-pad names such as `01_`, or pass the files explicitly as arguments.

Shell-style braces expand before the glob. Quote the argument so the shell leaves the braces intact. `{A,B}*.pdf` becomes `A*.pdf` and `B*.pdf`. Alternatives stay in the written order, and matches inside each alternative are ordered by path name. An alternative that matches nothing is skipped. The argument is an error only when every alternative matches nothing. A group without a comma, such as `{ABC}`, stays literal. This is brace expansion, not a regular expression.

If the same source name appears more than once with the same bytes, later copies are dropped. If several inputs share a source name but differ in bytes, the run errors. The `.pdf`, `.md`, and `.json` about to be written are excluded from the input.

Reruns follow `--update`. The default, `changed`, reuses a source whose source name, bytes, and OCR settings match the previous run, and rebuilds only sources whose bytes changed. `replace` rebuilds the sources passed this time. `keep` leaves an existing source name on its previous pages even when the bytes changed. Source names absent from the input stay. `--prune` drops them. When the result matches the previous run, files are not rewritten, except under `replace`.

`--lang` is `en` or `ja`. It selects the language of errors, help, and progress logs. The first run defaults to `en`. A later run, when `--lang` is omitted, uses `options.language` from the previous JSON. Passing `--lang` with a different value rewrites only that JSON field. The PDF and the Markdown stay as they are. `--dry-run` prints `language: ja -> en` when that field would change. Dry-run status names stay in English: `added`, `replaced`, `reused`, `kept`, `retained`, `pruned`, `capped`, and `same-content`.

The Markdown contains an English `## Notice` section. It does not follow `--lang`.

A previous JSON without `options.language`, or with a value other than `en` or `ja`, is an error. The message names the line where `"language": "en"` or `"language": "ja"` goes, inside `options`. `--update replace` and `--dry-run` stop as well.

`--dry-run` writes no files. It prints the outcome for each source name, then the pairs that have different names and the same bytes. That same-content list is the set before `--prune` is applied. The command still exits successfully when such pairs exist. A real run does not stop because of them. `changed` and `keep` with no previous JSON, and an empty input, fail the same way as a real run.

Symbolic links and directories are not replaced. During a run, `.{name}.pdf2context.lock` is placed at the output location, and a concurrent run is refused. If replacement fails, the previous output is restored.

Each external command is limited to `--timeout` seconds. The default is 600.

`--max-pdf-size` caps the merged PDF. Pass a byte count, or a number with a unit such as `32MB` (decimal) or `20MiB` (binary). Sources are added whole, in merge order. Retained, reused, and kept pages count toward the size. The size is the merged PDF after OCR. The first source that would make the PDF larger than the cap, and every source after it, is capped: it is left out of the PDF, the Markdown, and the JSON. A warning names each capped source. If no source fits, the run stops and the previous corpus stays as it is. Without this option there is no cap. `--dry-run` applies the same rule, prints `capped`, and writes no files.

## OCR

`--ocr` is `off`, `auto`, or `force`. The default is `off`. The default language is `jpn+eng`.

`--ocr-level` is `1`, `2`, or `3`. The default is `1`.

- `1` uses OCRmyPDF and Tesseract. `--jobs` is the OCRmyPDF worker count.
- `2` uses PP-OCRv6 small, from PaddleOCR 3.7.0 or newer.
- `3` uses PP-OCRv6 medium, from the same PaddleOCR.

Level 1 writes the recognized characters back into the PDF as an invisible text layer. The page looks the same, while search, copy, and a later `pdftotext` can read those characters. Skew is not corrected. The output is not converted to PDF/A. If the page count changes after OCR, the run stops. `force` regenerates the page images.

Levels 2 and 3 write the characters and rectangles from PaddleOCR onto the original page image. The page image is not redrawn. Skew is not corrected. The image sent to PaddleOCR is rendered at 300 dpi. Document rotation and unwarping stay off, so the rectangles remain on that image. One `paddleocr ocr` command runs for each recognized page, one page after another. `--jobs` does not change that. `--timeout` limits each of those commands. The default is 600 seconds. PaddleOCR uses a GPU when it finds one, and otherwise uses the CPU. There is no separate device option.

The font embedded for levels 2 and 3 is an installed Noto Sans CJK. Only the glyphs used on the page are embedded. Hiragino is not used. If `paddleocr` or Noto Sans CJK is missing, or recognition fails, the run stops and the previous corpus stays. The run does not fall back to level 1. A page that returns no characters keeps an empty text layer.

`--ocr off` ignores `--ocr-level`.

- `auto` leaves any page from which at least one character can be extracted as it is, and adds a text layer only to pages with no characters. A page that is only a page number, or an image with a single heading line, is left out entirely.
- `force` discards existing text and OCRs every page again. Use it for garbled text, or for an image whose only text is a caption.

Levels 2 and 3 accept only `jpn` and `eng` in `--ocr-lang`. The order does not matter. `eng+jpn` is the same as `jpn+eng`. Any other language stops the run before recognition.

Changing `--ocr-level` rebuilds that source. A previous JSON with no recognition level is level 1.

`--dry-run` checks that `paddleocr` and Noto Sans CJK are present for levels 2 and 3, and does not run recognition. With `--max-pdf-size`, those levels measure the PDF before the new text layer is added.

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
