[English](README.md) | [日本語](README.ja.md)

# pdf2context

複数の PDF を、一つのコーパスにまとめます。AI に渡すのは PDF と Markdown です。

`-o` には、拡張子を除いた出力パスを渡します。`/hoge/context/merged` なら、同じディレクトリに次の3ファイルができます。

- `/hoge/context/merged.pdf` — 結合した PDF。ページの見た目の正本です。
- `/hoge/context/merged.md` — ページごとの出典付きテキスト。
- `/hoge/context/merged.json` — 前回の出典を再利用するための記録です。出典、SHA-256、ページ本文が入ります。

AI に渡すのは `merged.pdf` と `merged.md` です。`merged.json` はこのツールのためのファイルです。AI には渡しません。

ページ見出しは、統合後のページ番号と、元ファイルのページ番号の両方を持ちます。本文はコードフェンスで囲みます。

```text
### contract.pdf — source p.4 — merged p.16
```

## 必要なもの

macOS では、Homebrew が formula とフォントの cask を一つのコマンドで入れます。

```bash
brew install qpdf poppler tesseract tesseract-lang font-noto-sans-cjk
```

`qpdf` と `poppler` は `pdftotext` を含み、いつも要ります。`tesseract` が要るのは認識レベル 1 だけです。`tesseract` 本体には英語が入っています。`tesseract-lang` は `jpn` を含むすべての Tesseract 言語を足し、レベル 1 の日本語に要ります。`font-noto-sans-cjk` が要るのはレベル 2 と 3 だけです。

`uv run` は [OCRmyPDF](https://ocrmypdf.readthedocs.io/)、`pypdfium2`、`paddleocr>=3.7.0`、`paddlepaddle==3.2.0` を入れます。ページの画像化には `pypdfium2` を使うので、Ghostscript は不要です。PaddleOCR、PaddlePaddle、[PP-OCRv6](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html) の small と medium の重みは Apache-2.0 で、このパッケージと同じです。`uv run` は `paddleocr` を `PATH` に通します。PaddlePaddle 3.2.0 の wheel は Python 3.11、3.12、3.13 にあります。Python 3.14 には無いので、そこではこの依存を外します。

Noto Sans CJK は SIL Open Font License 1.1 です。PDF に書いた字形は埋め込んでかまいません。使う書体は `NotoSansCJKjp-Regular.otf` です。ヒラギノは使いません。Debian と Ubuntu では `sudo apt install fonts-noto-cjk` です。Windows では [Noto CJK のリリース](https://github.com/notofonts/noto-cjk/releases) から `NotoSansCJKjp-Regular.otf` を、現在のユーザー向けにインストールします。

## 使い方

このリポジトリのルートで実行します。`uv run` がパッケージを仮想環境へ入れ、`pdf2context` コマンドとして起動します。`qpdf` と `pdftotext` は、「必要なもの」のとおり `PATH` に通しておきます。クローンしないときは、`uvx pdf2context` が PyPI 経由でパッケージを実行します。

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

`/hoge/context/pdf_a` を指定した場合のファイル名は `pdf_a.pdf`、`pdf_a.md`、`pdf_a.json` です。末尾が `.pdf`、`.md`、`.json` のときは、その拡張子を外してから同じ規則を適用します。

ディレクトリを渡すと、その直下の PDF をファイル名のコードポイント順で結合します。グロブは引数の順を保ち、一致したファイルはパス名の順です。`**/*.pdf` のように再帰もできます。`2.pdf` は `10.pdf` より後になります。順番を固定するときは `01_` のようにゼロ埋めするか、引数でファイルを直接並べてください。

シェルと同じ波括弧を、グロブの前に展開します。シェルに先に展開されないよう、引数は引用符で囲みます。`{A,B}*.pdf` は `A*.pdf` と `B*.pdf` になります。選択肢は書いた順のままで、各選択肢の一致はパス名の順です。一致が無い選択肢は飛ばします。すべての選択肢が一致しないときだけ、その引数はエラーです。カンマの無い `{ABC}` はそのままの文字です。これは正規表現ではなく、波括弧の展開です。

同じ出典名でバイト列も同じファイルが複数回現れた場合は、2 回目以降を除きます。出典名が同じでバイト列が違うものが一度に複数あるときは、エラーにします。これから書く `.pdf`、`.md`、`.json` は入力から除きます。

再実行は `--update` で決まります。既定の `changed` は、出典名とバイト列と OCR の指定が前回と同じ出典を再利用し、バイト列が変わった出典だけ作り直します。`replace` は今回渡した出典を作り直します。`keep` は、既存の出典名を、バイト列が変わっていても前回のページのまま残します。入力に無い出典名は残します。`--prune` を付けると、それらを除きます。結果が前回と同じときは、`replace` 以外はファイルを書き換えません。

`--lang` は `en` または `ja` です。エラー、ヘルプ、進捗ログの言語を選びます。初回の既定は `en` です。続きで `--lang` を省略したときは、前回の JSON の `options.language` を使います。`--lang` を付けて前回と違う値にしたときは、その JSON の項目だけを書き換えます。PDF と Markdown はそのままです。`--dry-run` は、その項目が変わるとき `language: ja -> en` と出します。予行の状態名は英語のままです。`added`、`replaced`、`reused`、`kept`、`retained`、`pruned`、`capped`、`same-content` です。

Markdown には英文の `## Notice` セクションがあります。`--lang` では変わりません。

前回の JSON に `options.language` が無いとき、または値が `en` と `ja` のどちらでもないときは、エラーです。メッセージは、`options` の中で `"language": "en"` または `"language": "ja"` を書く行を示します。`--update replace` と `--dry-run` も止まります。

`--dry-run` はファイルを書きません。先に各出典名の結果を出し、続けて別名でバイト列が同じ組を出します。この同内容の一覧は `--prune` を適用する前の集合です。同内容があっても終了は成功です。本実行は同内容では止まりません。前回の JSON が無いときの `changed` と `keep`、入力が空のときは、本実行と同じエラーになります。

シンボリックリンクやディレクトリは置き換えません。実行中は出力先に `.{名前}.pdf2context.lock` を置き、同時実行を拒みます。置き換えに失敗した場合は、以前の出力へ戻します。

各外部コマンドの制限時間は `--timeout` 秒です。既定は 600 秒です。

`--max-pdf-size` は、結合した PDF の最大サイズです。バイト数、または `32MB`（10進）や `20MiB`（2進）のように単位を付けて指定します。出典は結合順に、ファイルごと足します。残留、再利用、維持のページもサイズに数えます。大きさは、OCR のあとで結合した PDF のバイト数です。足すと上限を超える出典と、その後ろの出典は見送りです。PDF、Markdown、JSON のどれにも入りません。見送りは警告します。1件も収まらないときはエラーになり、前回のコーパスは残ります。このオプションが無いときは上限はありません。`--dry-run` も同じ判定をし、見送りは `capped` と出します。ファイルは書きません。

## OCR

`--ocr` は `off`、`auto`、`force` です。既定は `off` です。言語の既定値は `jpn+eng` です。

`--ocr-level` は `1`、`2`、`3` です。既定は `1` です。

- `1` は OCRmyPDF と Tesseract です。`--jobs` は OCRmyPDF のワーカー数です。
- `2` は PP-OCRv6 small です。PaddleOCR 3.7.0 以降を使います。
- `3` は PP-OCRv6 medium です。同じ PaddleOCR を使います。

レベル 1 は、認識した文字を透明な文字層として PDF に書き戻します。見た目は元のページのまま、検索、コピー、その後の `pdftotext` がその文字を読めます。傾き補正はしません。出力は PDF/A に変換しません。OCR の後にページ数が変わっていれば中止します。`force` はページ画像を作り直します。

レベル 2 と 3 は、PaddleOCR が返した文字と矩形を、元のページ画像の上に書きます。ページ画像は描き直しません。傾き補正はしません。PaddleOCR に渡す画像は 300 dpi で作ります。文書の回転と歪み補正はオフなので、矩形はその画像の上に残ります。認識するページごとに `paddleocr ocr` を1回、1ページずつ実行します。`--jobs` では変わりません。`--timeout` はそのコマンド1回の制限です。既定は 600 秒です。PaddleOCR は GPU があればそれを使い、無ければ CPU を使います。デバイスを別に指定するオプションはありません。

レベル 2 と 3 で埋め込むフォントは、インストール済みの Noto Sans CJK です。ページで使った字形だけを埋めます。ヒラギノは使いません。`paddleocr` か Noto Sans CJK が無いとき、または認識が失敗したときは、実行を止め、前回のコーパスを残します。レベル 1 には落としません。文字が返らなかったページは、空の文字層のままです。

`--ocr off` は `--ocr-level` を見ません。

- `auto` は、文字を1文字でも取り出せるページをそのままにし、文字のないページだけに文字層を足します。ページ番号だけのページや、見出しが1行ある画像も、ページ全体が対象外になります。
- `force` は、既存の文字を捨てて全ページを OCR し直します。文字化けや、キャプションだけ文字がある画像に使います。

レベル 2 と 3 の `--ocr-lang` は `jpn` と `eng` だけです。順序は問いません。`eng+jpn` は `jpn+eng` と同じです。それ以外の言語は、認識の前に止まります。

`--ocr-level` を変えると、その出典は作り直します。認識レベルの無い以前の JSON はレベル 1 です。

`--dry-run` は、レベル 2 と 3 では `paddleocr` と Noto Sans CJK があることだけを確認し、認識は走らせません。`--max-pdf-size` のとき、これらのレベルは新しい文字層を足す前の PDF の大きさで判定します。

## テキスト抽出

各ページを `pdftotext -f N -l N -nopgbrk -layout` で抽出します。ファイル全体を改ページ文字で分割しません。`-layout` を外すときは `--no-layout` を指定します。

JSON はコーパスの記録です。前回の JSON が無く、PDF か Markdown だけが残っているとき、`changed` と `keep` は止まります。作り直すときは `--update replace` を指定します。

## 出力しないもの

このツールは、表や見出しを Markdown の構造へ復元しません。OCR が拾うのは文字です。

暗号化された PDF は受け付けません。パスワードを外してから渡してください。

## 開発

```bash
uv run python -m unittest discover -s tests -v
```

## ライセンス

Apache License 2.0
