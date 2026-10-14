# 認識レベルで文字層の作り方を選ぶ

スキャンの文字の正答率を上げる指定を、既定の待ち時間と分けたい。認識レベル 1 は今の OCRmyPDF と Tesseract のまま。2 と 3 は、利用者が入れる PaddleOCR の PP-OCRv6 small と medium で、返った文字と矩形をページ画像の上に書き戻す。見た目の画像は全面を描き直さない。パッケージは Apache-2.0 のまま、PaddleOCR は依存に入れない。

## Considered Options

- Tesseract の再サンプルと `tessdata_best` だけ。公式の説明は、精度が少し上がり速度が大きく落ちる、である。
- レベル 3 を Surya OCR 2 などの視覚言語モデルにする。導入が二つになり、文字の位置は専用の検出器の方が高い、と PP-OCRv6 の論文が報告している。
- PP-OCRv6 tiny。日本語を含まない。

## Consequences

- レベル 2 と 3 で PaddleOCR が無い、または認識プロセスが失敗したときは、レベル 1 に落とさず止める。前回のコーパスは残る。
- `--ocr auto` は文字の無いページだけを、選んだレベルで読む。既にある文字層の文字化けを直すには `--ocr force` が要る。
- レベル 2 と 3 は、`--ocr-lang` が `jpn` と `eng` だけのとき、small または medium の一つのモデルを使う。それ以外の言語は実行前にエラーにする。
- 認識レベルを書いていない以前のコーパスは、レベル 1 として比較する。
- `--jobs` はレベル 1 の OCRmyPDF にだけ渡す。レベル 2 と 3 のページは直列に読む。
- レベル 2 と 3 の文字層に埋め込む日本語フォントは、システムに入っている Noto Sans CJK だけである。パッケージには同梱しない。ヒラギノがあっても使わない。無ければ止める。Noto Sans CJK は SIL Open Font License 1.1 で、文書への埋め込みが許される。README には、macOS、Linux、Windows での導入手順と、PaddleOCR の導入手順を書く。`README.md` と `README.ja.md` はその事実を同じく書く。
