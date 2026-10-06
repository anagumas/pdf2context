# pdf2context

複数の PDF を、一つのコーパスにまとめます。AI に渡すのは PDF と Markdown です。

`-o` には、拡張子を除いた出力パスを渡します。`/hoge/context/merged` なら、同じディレクトリに次の3ファイルができます。

- `/hoge/context/merged.pdf` — 結合した PDF。ページの見た目の正本です。
- `/hoge/context/merged.md` — ページごとの出典付きテキスト。
- `/hoge/context/merged.json` — 前回の出典を再利用するための記録です。出典、SHA-256、ページ本文が入ります。

ページ見出しは、統合後のページ番号と、元ファイルのページ番号の両方を持ちます。本文はコードフェンスで囲みます。

```text
### contract.pdf — source p.4 — merged p.16
```

## 必要なもの

PDF の結合とテキスト抽出には、次のコマンドが必要です。

```bash
brew install qpdf poppler
```

OCR は [OCRmyPDF](https://ocrmypdf.readthedocs.io/) が行います。パッケージは `uv run` が入れます。ページの画像化には、同時に入る `pypdfium2` を使うので、Ghostscript は不要です。

OCR を使うときだけ、Tesseract 本体が必要です。`brew install tesseract` には英語の学習データが入っています。全言語パック `tesseract-lang` は不要です。日本語を読むときは `jpn.traineddata` だけ追加します。

```bash
brew install tesseract
curl -L "https://github.com/tesseract-ocr/tessdata/raw/main/jpn.traineddata" \
  -o "$(brew --prefix)/share/tessdata/jpn.traineddata"
```

## 使い方

このリポジトリのルートで実行します。`uv run` がパッケージを仮想環境へ入れ、`pdf2context` コマンドとして起動します。

```bash
uv run pdf2context '/hoge/pdf_a/*.pdf' -o /hoge/context/merged
uv run pdf2context '/hoge/pdf_a/*.pdf' -o /hoge/context/pdf_a
uv run pdf2context docs/ -o output/merged
uv run pdf2context --ocr auto --ocr-lang jpn+eng shots/*.pdf -o output/merged
uv run pdf2context --ocr force --update replace shots/*.pdf -o output/merged
uv run pdf2context --dry-run --prune shots/*.pdf -o output/merged
```

`/hoge/context/pdf_a` を指定した場合のファイル名は `pdf_a.pdf`、`pdf_a.md`、`pdf_a.json` です。末尾が `.pdf`、`.md`、`.json` のときは、その拡張子を外してから同じ規則を適用します。

ディレクトリを渡すと、その直下の PDF をファイル名のコードポイント順で結合します。グロブは引数の順を保ち、一致したファイルはパス名の順です。`**/*.pdf` のように再帰もできます。`2.pdf` は `10.pdf` より後になります。順番を固定するときは `01_` のようにゼロ埋めするか、引数でファイルを直接並べてください。

同じ出典名でバイト列も同じファイルが複数回現れた場合は、2 回目以降を除きます。出典名が同じでバイト列が違うものが一度に複数あるときは、エラーにします。これから書く `.pdf`、`.md`、`.json` は入力から除きます。

再実行は `--update` で決まります。既定の `changed` は、出典名とバイト列と OCR の指定が前回と同じ出典を再利用し、バイト列が変わった出典だけ作り直します。`replace` は今回渡した出典を作り直します。`keep` は、既存の出典名を、バイト列が変わっていても前回のページのまま残します。入力に無い出典名は残します。`--prune` を付けると、それらを除きます。結果が前回と同じときは、`replace` 以外はファイルを書き換えません。

`--dry-run` はファイルを書きません。先に各出典名の結果を出し、続けて別名でバイト列が同じ組を出します。この同内容の一覧は `--prune` を適用する前の集合です。同内容があっても終了は成功です。本実行は同内容では止まりません。前回の JSON が無いときの `changed` と `keep`、入力が空のときは、本実行と同じエラーになります。

シンボリックリンクやディレクトリは置き換えません。実行中は出力先に `.{名前}.pdf2context.lock` を置き、同時実行を拒みます。置き換えに失敗した場合は、以前の出力へ戻します。

各外部コマンドの制限時間は `--timeout` 秒です。既定は 600 秒です。

## OCR

`--ocr` は `off`、`auto`、`force` です。既定は `off` です。言語の既定値は `jpn+eng` です。

OCRmyPDF は、認識した文字を透明な文字層として PDF に書き戻します。見た目は元のページのまま、検索、コピー、その後の `pdftotext` がその文字を読めます。傾き補正はしません。出力は PDF/A に変換しません。OCR の後にページ数が変わっていれば中止します。

- `auto` は、文字を1文字でも取り出せるページをそのままにし、文字のないページだけに文字層を足します。ページ番号だけのページや、見出しが1行ある画像も、ページ全体が対象外になります。
- `force` は、既存の文字を捨てて全ページを OCR し直します。文字化けや、キャプションだけ文字がある画像に使います。ページ画像は作り直されます。

## テキスト抽出

各ページを `pdftotext -f N -l N -nopgbrk -layout` で抽出します。ファイル全体を改ページ文字で分割しません。`-layout` を外すときは `--no-layout` を指定します。

JSON はコーパスの記録です。前回の JSON が無く、PDF か Markdown だけが残っているとき、`changed` と `keep` は止まります。作り直すときは `--update replace` を指定します。

## 出力しないもの

このツールは、表や見出しを Markdown の構造へ復元しません。Slack の画面キャプチャから、投稿者、時刻、返信、引用の関係も復元しません。OCR が拾うのは文字です。

暗号化された PDF は受け付けません。パスワードを外してから渡してください。

## 開発

```bash
uv run python -m unittest discover -s tests -v
```

## ライセンス

Apache License 2.0
