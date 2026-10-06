"""Messages for errors, help, and progress logs."""

from __future__ import annotations

from contextvars import ContextVar

LANGUAGE: ContextVar[str] = ContextVar("pdf2context_language", default="en")

CATALOG: dict[str, dict[str, str]] = {
    "en": {
        "output_path_no_name": "Output path has no file name: {path}",
        "output_path_directory": (
            "Output path is a directory; pass a file stem without an extension: {path}"
        ),
        "timed_out": "{name}: timed out after {timeout} seconds.",
        "cannot_run": "Cannot run {command}: {error}",
        "encrypted_hint": "Remove the password from encrypted PDFs before passing them.",
        "tool_failed": "{tool} failed (exit code {returncode}).\n{detail}{hint}",
        "ocr_mode": "OCR mode must be off, auto, or force.",
        "update_mode": "Update mode must be changed, replace, or keep.",
        "ocr_lang_empty": "OCR language is empty. Example: jpn+eng",
        "jobs": "OCR jobs must be at least 1.",
        "timeout_positive": "Timeout must be a positive number of seconds.",
        "not_pdf": "Not a PDF: {path}",
        "excluded_output": "Excluded an output file from the input: {path}",
        "no_inputs_left": "No input PDFs remain after excluding the output files.",
        "no_pdfs_found": "No PDFs found: {argument}",
        "directory_empty": "Directory contains no PDFs: {path}",
        "input_not_found": "Input not found: {argument}",
        "same_name_different_bytes": "Same source name with different bytes: {name}",
        "duplicate_input": "Excluded a duplicate input: {path}",
        "not_regular_file": "Refusing to replace anything other than a regular file: {path}",
        "previous_json_missing": (
            "Previous JSON is missing. A JSON record is required to continue. "
            "Pass --update replace to rebuild."
        ),
        "cannot_read_json": "Cannot read the previous JSON: {path}",
        "unsupported_schema": "Unsupported schema_version in this JSON.",
        "invalid_json_shape": "Previous JSON has an invalid shape: {path}",
        "duplicate_source_names": "Previous JSON contains duplicate source names: {name}",
        "output_locked": "Output is locked: {path}. Delete the lock if no run is in progress.",
        "unchanged": "No changes.",
        "done": "Done: {pages} pages ({empty} without text).",
        "no_text_warning": "Some pages have no text. For scanned images, try --ocr auto.",
        "inputs_count": "Inputs: {count} files.",
        "tesseract_list_failed": "Could not list Tesseract languages.\n{detail}",
        "tesseract_missing_lang": (
            "Tesseract has no trained data for: {codes}\n"
            "The tesseract package includes English. For Japanese, add jpn.traineddata "
            "to the tessdata directory."
        ),
        "missing_commands": "Missing required commands: {commands}",
        "no_input_pdfs": "No input PDFs.",
        "merged_count_mismatch": "Merged page count does not match the sources.",
        "ocr_page_count": "Page count changed after OCR: {path}",
        "previous_pdf_missing": "Previous PDF is missing. Cannot extract the remaining pages.",
        "previous_page_count": "Previous page count does not match the source: {name}",
        "input_changed": "Input file changed while being copied: {source}",
        "page_count_unreadable": "Could not read the page count: {path}",
        "pdf_has_no_pages": "PDF has no pages: {path}",
        "language_missing": (
            '{path}:{line}: Add "language": "en" or "language": "ja" inside options.'
        ),
        "language_invalid": '{path}:{line}: language must be "en" or "ja".',
        "language_updated": "Updated language to {language}: {path}",
        "interrupted": "Interrupted.",
        "expected_positive_int": "Expected a positive integer.",
        "expected_positive_number": "Expected a positive number.",
        "description": (
            "Merge PDFs into a .pdf, .md, and .json corpus with page-level source citations."
        ),
        "help_inputs": "PDF files, a directory of PDFs, or a glob",
        "help_output": (
            "Output path without an extension (default: merged). Example: /hoge/context/merged"
        ),
        "help_ocr": "off: no OCR. auto: pages with no characters. force: OCR every page again",
        "help_ocr_lang": "Tesseract languages (default: jpn+eng)",
        "help_jobs": "OCR worker count (default: 1)",
        "help_timeout": "Timeout in seconds for each external command (default: 600)",
        "help_no_layout": "Omit pdftotext -layout",
        "help_update": (
            "changed: rebuild sources whose bytes changed (default). "
            "replace: rebuild the sources passed this time. "
            "keep: leave an existing source name on its previous pages"
        ),
        "help_prune": "Drop source names that are absent from this input",
        "help_dry_run": "Write nothing. Print the plan and same-content groups",
        "help_quiet": "Suppress the completion message",
        "help_lang": (
            "Language of errors, help, and progress logs: en or ja. "
            "The first run defaults to en. A later run uses options.language when this is omitted"
        ),
    },
    "ja": {
        "output_path_no_name": "出力パスにファイル名がありません: {path}",
        "output_path_directory": (
            "出力パスはディレクトリではなく、拡張子を除いたファイル名です: {path}"
        ),
        "timed_out": "{name}: {timeout} 秒でタイムアウトしました。",
        "cannot_run": "実行できません: {command}: {error}",
        "encrypted_hint": "暗号化された PDF は、パスワードを外してから渡してください。",
        "tool_failed": "{tool} が失敗しました（終了コード {returncode}）。\n{detail}{hint}",
        "ocr_mode": "OCR モードは off、auto、force のいずれかです。",
        "update_mode": "更新方法は changed、replace、keep のいずれかです。",
        "ocr_lang_empty": "OCR 言語が空です。例: jpn+eng",
        "jobs": "OCR の並列数は 1 以上です。",
        "timeout_positive": "タイムアウトは正の秒数です。",
        "not_pdf": "PDF ではありません: {path}",
        "excluded_output": "出力ファイルを入力から除外しました: {path}",
        "no_inputs_left": "出力ファイルと重複を除くと、入力 PDF が残りません。",
        "no_pdfs_found": "PDF が見つかりません: {argument}",
        "directory_empty": "ディレクトリに PDF がありません: {path}",
        "input_not_found": "入力が見つかりません: {argument}",
        "same_name_different_bytes": "同じ出典名で内容が違います: {name}",
        "duplicate_input": "重複した入力を除外しました: {path}",
        "not_regular_file": "通常のファイル以外は置き換えません: {path}",
        "previous_json_missing": (
            "前回の JSON がありません。続きを判断するには JSON が必要です。"
            "作り直すときは --update replace を指定してください。"
        ),
        "cannot_read_json": "前回の JSON を読めません: {path}",
        "unsupported_schema": "この JSON の schema_version には対応していません。",
        "invalid_json_shape": "前回の JSON の形が不正です: {path}",
        "duplicate_source_names": "前回の JSON に同じ出典名が複数あります: {name}",
        "output_locked": "出力がロックされています: {path}。実行中でなければ削除してください。",
        "unchanged": "変更はありません。",
        "done": "完了: {pages} ページ（テキストなし {empty}）。",
        "no_text_warning": "テキストのないページがあります。スキャン画像なら --ocr auto を検討してください。",
        "inputs_count": "入力: {count} ファイル。",
        "tesseract_list_failed": "Tesseract の言語一覧を読めませんでした。\n{detail}",
        "tesseract_missing_lang": (
            "Tesseract に学習データがありません: {codes}\n"
            "tesseract 本体には英語が入っています。日本語は jpn.traineddata を "
            "tessdata ディレクトリへ追加してください。"
        ),
        "missing_commands": "必要なコマンドがありません: {commands}",
        "no_input_pdfs": "入力 PDF がありません。",
        "merged_count_mismatch": "結合後のページ数が出典と一致しません。",
        "ocr_page_count": "OCR の後でページ数が変わりました: {path}",
        "previous_pdf_missing": "前回の PDF がありません。続きのページを取り出せません。",
        "previous_page_count": "前回のページ数が出典と一致しません: {name}",
        "input_changed": "入力のコピー中にファイルが変わりました: {source}",
        "page_count_unreadable": "ページ数を読めませんでした: {path}",
        "pdf_has_no_pages": "ページがありません: {path}",
        "language_missing": (
            '{path}:{line}: options の中に "language": "en" または "language": "ja" を追加してください。'
        ),
        "language_invalid": '{path}:{line}: language は "en" か "ja" にしてください。',
        "language_updated": "表示言語を {language} に更新しました: {path}",
        "interrupted": "中断しました。",
        "expected_positive_int": "正の整数を指定してください。",
        "expected_positive_number": "正の数を指定してください。",
        "description": "複数の PDF を結合し、ページ単位の出典を持つ .pdf / .md / .json を作ります。",
        "help_inputs": "PDF ファイル、PDF が入ったディレクトリ、またはグロブ",
        "help_output": "拡張子を除いた出力パス（既定: merged）。例: /hoge/context/merged",
        "help_ocr": "off: OCR しない。auto: 文字のないページだけ。force: 全ページを OCR し直す",
        "help_ocr_lang": "Tesseract の言語（既定: jpn+eng）",
        "help_jobs": "OCR の並列数（既定: 1）",
        "help_timeout": "外部コマンド 1 回のタイムアウト秒（既定: 600）",
        "help_no_layout": "pdftotext の -layout を外す",
        "help_update": (
            "changed: 内容が変わった出典だけ作り直す（既定）。"
            "replace: 今回渡した出典を作り直す。"
            "keep: 既存の出典名は前回のページを残す"
        ),
        "help_prune": "今回の入力に無い出典名をコーパスから除く",
        "help_dry_run": "ファイルを書かず、予行と同内容の一覧を表示する",
        "help_quiet": "完了メッセージを出さない",
        "help_lang": (
            "エラー、ヘルプ、進捗ログの言語。en または ja。"
            "初回の既定は en。続きで省略したときは JSON の language を使う"
        ),
    },
}


def say(key: str, **kwargs: object) -> str:
    return CATALOG[LANGUAGE.get()][key].format(**kwargs)
