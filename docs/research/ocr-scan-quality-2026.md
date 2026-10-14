# スキャン OCR の品質を上げる選択肢（2026-10-14）

調査日は 2026-10-14。対象はローカル CLI `pdf2context`（Apache-2.0）。いまの OCR は、外部プロセスの OCRmyPDF が Tesseract を呼び、認識文字を PDF の不可視テキスト層へ書き戻す。表や見出しは Markdown の構造へ戻さない。既定の OCR 言語は `jpn+eng`。傾き補正はしない。ラスタ化は `pypdfium2` で、Ghostscript は使わない。出典はリポジトリの README と実装。

- https://github.com/anagumas/pdf2context/blob/main/README.md （手元の `README.md` の OCR 節と同じ記述）
- 実装が渡している引数は `--skip-text` または `--force-ocr`、`--output-type pdf`、`--optimize 0`、`-l`、`-j` だけである。`--deskew` は渡していない。`src/pdf2context/pipeline.py` の `_materialize_source`

このメモはエンジンを一つに決めない。数値とライセンスは、下に書いた一次 URL の範囲だけを使う。ライセンス文書が複数あって条件がずれるときは「曖昧」と書く。

## 1. 過去にライセンスで外した OCR エンジン

**見つからなかった。** OCR エンジンの名前を、ライセンスを理由に却下した記録は、次の範囲に無かった。

- リポジトリの `README.md`、`README.ja.md`、`GLOSSARY.md`、`docs/adr/`、`docs/agents/`
- `/Users/tetsuya_masunaga/.cursor/projects/Users-tetsuya-masunaga-Develop-pdf2context/agent-transcripts` の既存会話
- 同じマシンの他の Cursor プロジェクト会話フォルダ（`Develop`、`adjust-fax-pdf`、`fax-ready-pdf`、`empty-window`）と、ユーザーの agent store

PaddleOCR、Surya、EasyOCR、docTR、olmOCR、MinerU、GOT-OCR、Chandra、DeepSeek-OCR、dots.ocr を、この範囲の過去会話がライセンス理由で外した記述は無い。

### ライセンスで外したのは PDF ライブラリであり、OCR エンジンではない

会話 `50a6c41e-4a5f-4e6d-bec4-7c180446cd88` のアシスタント返答に、次の文がある。

> このリポジトリは Apache License 2.0 です。PyMuPDF は AGPL か商用ライセンスなので、配布する本体に組み込む選択とはライセンスが合いません。

PyMuPDF は PDF の結合・描画・抽出のライブラリである。この文は OCR エンジンの却下ではない。PyPI の当該パッケージは「Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License」と書いている。

- https://pypi.org/project/pymupdf/

同じ会話では、Docling を表や見出しが崩れる通常の資料との比較対象に限ると書いている。ライセンスで外したとは書いていない。会話 `d3d66dfb-f58e-44de-9e20-78a9f71ceaf1` は、表や見出しの構造化を最初から対象外とし、その需要の例として LlamaParse、Docling、Unstructured を挙げている。これもライセンス却下ではない。

## 2. いまの経路で、Tesseract に既にある前処理

Tesseract 5 の利用者向け説明は tessdoc にある。学習データは 4.0.0 以降のものを 5.x でも使う。

- https://tesseract-ocr.github.io/tessdoc/
- コードのライセンスは Apache-2.0。https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE
- 外部プロセスにできる。`tesseract` コマンドがある。Apache-2.0 のパッケージへ import しなくても起動できる。

### 公式が品質について書いていること

https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html

- 少なくとも 300 dpi の画像が向く。解像度が足りないときは拡大する。
- 二値化は内部で Otsu をかける。背景の濃さが一様でないと失敗する。Tesseract 5.0.0 以降は Adaptive Otsu と Sauvola があり、`tesseract --print-parameters | grep thresholding_` でパラメータを見る。
- 傾きが大きいと行分割が落ちる。文字行が水平になるよう回す。
- 既定のページ分割は、1ページの文章を想定する。縦書きの一様なブロックは `--psm 5`（「Assume a single uniform block of vertically aligned text」）。既定は `--psm 3`。
- 表は、独自の領域分割を足さないと苦手だと書いている。

`jpn_vert` は縦書き日本語の学習データである。`tessdata_best` に `jpn_vert.traineddata` がある。

- https://github.com/tesseract-ocr/tessdata_best/blob/main/jpn_vert.traineddata
- https://tesseract-ocr.github.io/tessdoc/Data-Files-in-tessdata_best.html （`jpn_vert` のネットワーク仕様を掲載）

`tessdata_best` は速度をかなり犠牲にして精度を少し上げる LSTM モデルで、`--oem 1` 専用である。再学習の起点にもこれだけが使える、と tessdoc は書く。日付の記載は 2017 年の学習データである。

- https://tesseract-ocr.github.io/tessdoc/Data-Files.html （`tessdata_best` は精度寄りで遅く、float。`tessdata` は legacy と、integer 化した LSTM の両方）
- `tessdata_best` リポジトリの README は、中身を Apache-2.0 としている。https://github.com/tesseract-ocr/tessdata_best/blob/main/README.md
- `tessdata` リポジトリの LICENSE も Apache-2.0 である。https://github.com/tesseract-ocr/tessdata/blob/main/LICENSE

縦書きで `--psm 3` が崩れた事例と、`--psm 5` なら読めた事例は、Tesseract の issue にある。メンテナは `--psm 5` を使うよう答え、その後 `main` で当該不具合は直ったと報告されている。これは「縦書きなら常に psm 5」という公式マニュアルの一文ではない。psm 5 の定義は、ページ全体が縦書きの一様なブロックである場合である。横書きと縦書きが混在するページに、ページ全体へ psm 5 を掛ける前提ではない。

- https://github.com/tesseract-ocr/tesseract/issues/3997

### OCRmyPDF が既に露出しているもの

OCRmyPDF のコードは MPL-2.0 である。

- https://github.com/ocrmypdf/OCRmyPDF/blob/main/LICENSE
- https://github.com/ocrmypdf/OCRmyPDF/blob/main/pyproject.toml （`license = "MPL-2.0"`）

コマンド `ocrmypdf` として外部プロセスにできる。このリポジトリは既にそうしている。MPL-2.0 のソースを Apache-2.0 のパッケージへどう組み込むかは、このメモでは判断しない。

Cookbook と advanced が書いている、スキャン品質に関係するオプションは次のとおり。pdf2context はどれも渡していない。

| オプション | 公式の説明 | 出典 |
| --- | --- | --- |
| `--deskew` | 斜めのスキャンを水平へ戻してから OCR する。90度単位の向きは `--rotate-pages` の役割 | https://ocrmypdf.readthedocs.io/en/latest/cookbook.html |
| `--rotate-pages` | ページの向きを推定して回す。閾値は `--rotate-pages-threshold`。既定は保守的 | 同上 |
| `--oversample DPI` | OCR の前に、指定 dpi 以上へ再サンプルする | 同上の “Improving OCR quality” |
| `--clean` | unpaper で OCR 前だけ掃除する。出力画像は変えない | 同上 |
| `--clean-final` | 掃除した画像を成果物にも入れる。見落としがないか目視するよう警告している | 同上 |
| `--remove-background` | グレーまたはカラーの背景ノイズを落とす。モノクロは無視。写真を消すことがある | 同上 |
| `--tesseract-pagesegmode` | Tesseract の psm を渡す。既定は 3。0、1、2、12 は OCRmyPDF と両立しない。OCRmyPDF は OSD を OCR と別ステップで行う | https://ocrmypdf.readthedocs.io/en/latest/advanced.html |
| `-l` | 言語。`eng+fra` のような結合を例示している。言語の自動判定は無い | cookbook |
| `--rasterizer pypdfium` | 17.0.0 以降。既定の `auto` は pypdfium2 を優先する。Ghostscript も選べる | cookbook の “Select a rasterizer” |
| `--output-type pdf` | PDF/A にしない | cookbook |

`--deskew` を使うと、元ページを全面ラスタ化してから文字層を載せる、と advanced は書く。見た目を保ったまま文字層だけ足す経路ではなくなる。

- https://ocrmypdf.readthedocs.io/en/latest/advanced.html

Debian testing の man page は、さらに `--tesseract-oem`、`--tesseract-thresholding`、`--tesseract-config`、`--image-dpi` を列挙している。`--image-dpi` は、入力が PDF ではなく画像のときの解像度である。readthedocs の advanced ページ本文では、この調査で `--tesseract-thresholding` の説明位置を確認していない。man page を出典にする。

- https://manpages.debian.org/testing/ocrmypdf/ocrmypdf.1.en.html

したがって、300 dpi への再サンプル、傾き補正、unpaper による前処理、psm、`jpn_vert`、`tessdata_best` は、OCRmyPDF か Tesseract の側に既にある。pdf2context が今日渡しているのは言語コード（既定 `jpn+eng`）と、`--skip-text` / `--force-ocr`、`--output-type pdf`、`--optimize 0` である。`tessdata_best` を指す設定は、このリポジトリの起動引数には無い。Tesseract は `TESSDATA_PREFIX` のデータを使う。

## 3. 候補

「外部プロセス」は、公式がコマンド起動を書いているかを指す。Python の import が README の手順でも、別インタプリタで起動すればプロセスは分けられる。その場合は「公式 CLI は README に無い」と書く。

「PDF 文字層」は、元のスキャンページの上へ不可視の文字を戻すことを指す。別形式の Markdown や、解析結果から組み直した PDF は、文字層ではない。

### Tesseract 5 と OCRmyPDF

上の第 2 節のとおり。出力は PDF の文字層（Tesseract 単体も `tesseract image output pdf` を cookbook が例示している）。日本語は `jpn` と縦書きの `jpn_vert`。実行は CPU の外部プロセス。モデルは学習データファイルで、`tessdata_best` の `jpn_vert.traineddata` は約 14 MB と GitHub のファイル表示が書いている（14,330,809 bytes）。

- https://github.com/tesseract-ocr/tessdata_best/blob/main/jpn_vert.traineddata

2025年や 2026年の新しい Tesseract 本体リリースは、この調査の対象日付としては置かない。学習データの説明は 2017 年のままである。

### PaddleOCR / PP-OCRv5 / PP-OCRv6 / PaddleOCR-VL / HPD-Parsing

- 一次 URL: https://github.com/PaddlePaddle/PaddleOCR
- コードも、PaddleOCR-VL の Hugging Face LICENSE も Apache-2.0。https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE と https://huggingface.co/PaddlePaddle/PaddleOCR-VL/blob/main/LICENSE
- README は、PDF と画像を JSON / Markdown の構造化データにすると書く。不可視の PDF 文字層とは書いていない。
- ハードウェアのバッジは CPU、GPU、XPU、NPU。

README の更新履歴（https://github.com/PaddlePaddle/PaddleOCR/blob/main/README.md ）:

| 日付 | 名前 | README が書いていること |
| --- | --- | --- |
| 2025-10-16（リリース v3.3.0） | PaddleOCR-VL | 0.9B。NaViT 風の視覚エンコーダと ERNIE-4.5-0.3B。109 言語。文字、表、式、図。https://github.com/PaddlePaddle/PaddleOCR/releases/tag/v3.3.0 |
| 2025（技術報告 arXiv:2507.05595） | PP-OCRv5 | 簡体字・繁体字・ピンイン・英語・日本語を一つの認識モデルで扱う、と著者の技術報告が書く。パラメータは 1 億未満のパイプライン、と要約している。https://arxiv.org/abs/2507.05595 |
| 2026-05-28（PaddleOCR 3.6.0） | PaddleOCR-VL-1.6 | 0.9B。OmniDocBench v1.6 で 96.3% 超、と README が書く。表、古文書、稀字、印鑑、図。Hugging Face: https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6 |
| 2026-06-11（PaddleOCR 3.7.0） | PP-OCRv6 | 中国語・英語・日本語と、ラテン文字 46 言語。tiny 1.5M / small 7.7M / medium 34.5M。medium は PP-OCRv5_server より検出 +4.6%、認識 +5.1%、と README が書く。CPU（OpenVINO）で 5.2 倍、Apple M4 の tiny で 6.1 倍、A100 で 0.13 秒、とも書く。公式チュートリアルは、tiny は `japan` を含まない、と書く。small と medium は含む。ローカルコマンドは `paddleocr ocr`。結果の `rec_boxes` は各文字行の矩形。`paddleocr api` は公式 API 向けで、ローカル推論ではない。https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html と https://arxiv.org/html/2606.13108v1 |
| 2026-07-22 | HPD-Parsing | 高スループットの文書解析 VLM。公開ベンチでピーク 4,752 tokens/s、と README が書く。日本語とは書いていない。vLLM。チュートリアル: https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/HPD-Parsing.html |

日本語は、PP-OCRv5 の技術報告、PP-OCRv6 のリリースノート、PaddleOCR-VL の「109 言語」に含まれる、とそれぞれの一次文書が書く。VL の 109 言語の一覧に日本語の行があるかは、この調査では言語リスト原文まで開いていない。v3.3.0 の文は「中国語を含む主要言語」と例示し、日本語をその文の例には出していない。PP-OCRv6 は日本語を名指ししている。

外部プロセス: README 先頭はライブラリとしての説明である。HPD-Parsing は OpenAI 互換サーバとローカル推論を書いている。`paddleocr` コマンドの現行フラグは、この調査では公式チュートリアル HTML の本文抽出まで到達していない。

### Surya（Surya OCR 2）

- 一次 URL: https://github.com/datalab-to/surya
- コードは Apache-2.0。重みは modified AI Pubs OpenRAIL-M。README は「研究、個人利用、資金調達または売上が 500 万ドル未満のスタートアップは無料。それ以外の商用は別ライセンス」と書く。
- 2025 年の citation（`paruchuri2025surya`）がある。README が今説明している本体は Surya OCR 2 で、0.65B（650M）の一つの VLM がレイアウト、OCR、表を扱う。2026 年の日付は README からこの調査では取れていない。
- 日本語: 内部ベンチの表に `ja` / Japanese 86.2% がある。91 言語で総合 87.2%、と README が書く。
- 出力は json（ボックス付き）、markdown、html。PDF 文字層とは書いていない。
- 実行: `surya_ocr` などのコマンド。初回に vLLM（NVIDIA GPU）または llama.cpp のサーバを起動する。README は RTX 5090 で 5 pages/s（96 DPI の文脈が近くにある）と書く。
- 外部プロセスにできる。

### EasyOCR

- 一次 URL: https://github.com/JaidedAI/EasyOCR
- リポジトリの LICENSE は Apache-2.0。https://github.com/JaidedAI/EasyOCR/blob/master/LICENSE
- 重み: README は、選んだ言語の重みを `~/.EasyOCR/model` へ落とすと書き、検出は CLOVA の CRAFT 学習済みモデルを使うと書く。EasyOCR の LICENSE ファイルは CRAFT 重みの別ライセンスを付けていない。CRAFT 側の LICENSE はこの調査では開いていない。検出重みのライセンスは曖昧。
- 日本語: `easyocr/easyocr.py` が言語リストに `ja` を含むとき `japanese_g2` を選ぶ。https://github.com/JaidedAI/EasyOCR/blob/master/easyocr/easyocr.py
- 出力は、README の使い方が Python で文字列とボックスを返す形である。PDF 文字層とは書いていない。
- 実行: GPU が無いときは `gpu=False` で CPU、と README が書く。公式 CLI は README に無い。別プロセスにするには、利用者側の Python スクリプトが要る。
- 2025年または 2026年の新しいモジュール、とは README から確認していない。

### docTR

- 一次 URL: https://github.com/mindee/doctr
- コードは Apache-2.0。`doctr/datasets/vocabs.py` の先頭も Apache-2.0 と書く。
- 日本語: 同じファイルが `VOCABS["japanese"]` を定義し、ひらがな、カタカナ、常用漢字を連結している。https://github.com/mindee/doctr/blob/main/doctr/datasets/vocabs.py
- README の Quick Tour は、検出してから単語を読む二段構成と、事前学習モデルの選択を書く。日本語の事前学習チェックポイントを README は名指ししていない。語彙定義と、配布されている重みが日本語をカバーすることは別である。後者は未確認。
- 出力は単語位置と文字。PDF 文字層とは書いていない。GPU 用 Docker は CUDA 12.2 以上、と README が書く。CPU 専用の所要時間は README から取っていない。
- 公式 CLI は、この調査で読んだ README には無かった。
- 2025–2026 の新モデル発表は、README からは確認していない。`vocabs.py` の著作権表示は 2021–2026 である。

### GOT-OCR2.0

- 一次 URL: https://github.com/Ucas-HaoranWei/GOT-OCR2.0
- 実在する。README は 2024-09-03 にモデルを公開したと書く。2025–2026 の新しいリリースではない。
- ライセンスは曖昧。README のバッジは Code License Apache-2.0 と Data License CC BY-NC 4.0 だが、どちらも Stanford Alpaca の LICENSE / DATA_LICENSE へリンクしている。GOT 自身の LICENSE ファイルは、リポジトリ直下の一覧に無かった。
- 別のモデルカード https://huggingface.co/stepfun-ai/GOT-OCR2_0 は `license: apache-2.0` と `language: multilingual` を書く。日本語とは書いていない。GitHub バッジとこのモデルカードは一致しない。
- 推論例は Python。公式の単一 CLI は、この調査で読んだ README 範囲では確認していない。PDF 文字層とは書いていない。
- パラメータ数は、この GOT の README からは取っていない。

### olmOCR

- 一次 URL: https://github.com/allenai/olmocr
- README はプロジェクトを Apache-2.0 とする。https://github.com/allenai/olmocr/blob/main/LICENSE
- 2025-10-21 に v0.4.0、モデル `allenai/olmOCR-2-7B-1025-FP8`。7B の VLM で GPU が要る、と README が書く。ローカル GPU は 12 GB 以上の GPU RAM と、空きディスク 30 GB を要件にしている。
- 出力は Markdown（プレーンテキストへ線形化する、とも冒頭が書く）。PDF 文字層とは書いていない。
- 日本語は README に無い。CLI の `--apply_filter` は「英語の PDF で、フォームでなく、SEO スパムらしくないもの」を選ぶ、と README のヘルプ文が書く。
- 外部プロセスにできる。`olmocr` コマンドと、遠隔の OpenAI 互換サーバを指す手順がある。
- 2026 年の新しい olmOCR リリースは、この調査で読んだ README の News には無かった。

### MinerU

- 一次 URL: https://github.com/opendatalab/MinerU
- ライセンスは Apache-2.0 に追加条件がある。https://github.com/opendatalab/MinerU/blob/master/LICENSE.md
- 追加条件の要旨: 商用は原則として別ライセンス無しでよい。ただし関係会社を合わせて月間アクティブユーザが 1 億を超える、または月間売上が 2,000 万米ドルを超える場合は別の商用ライセンスが要る。第三者向けオンラインサービスでは MinerU を使っていると表示する。
- README は MinerU 4.0 を説明し、スキャン PDF と画像の OCR、Markdown を含む複数の書き出し（HTML、LaTeX、DOCX、EPUB、PDF、構造化コンテンツ）を書く。ここでの PDF は書き出し形式の一つであり、元スキャンへ不可視文字層を戻すとは書いていない。
- 英語 README は日本語 OCR を名指ししていない。品質段の中国語名は表示名である。
- 外部プロセスにできる。`mineru` コマンドを README が例示している。CPU と GPU の所要時間は、この調査で読んだ範囲では数値を取っていない。
- 2026 年の特定バージョン日付は、英語 README の先頭からは取っていない。GitHub API は LICENSE の SPDX を `NOASSERTION` として返す。条件は LICENSE.md を見る。

### dots.ocr と dots.mocr

- 一次 URL: https://github.com/studio-dots-ai/dots.ocr と https://github.com/studio-dots-ai/dots.mocr
- 2026-03-19 に dots.ocr-1.5 を dots.mocr として出した、と dots.ocr の README が書く。論文 https://arxiv.org/abs/2603.13032 。重み https://huggingface.co/rednote-hilab/dots.mocr
- Hugging Face のカードは `license: mit`、`language: en, zh, multilingual`。日本語とは書いていない。
- ライセンスは曖昧、というより二枚ある。`LICENSE` は MIT（copyright 2025 rednote-hilab）。同じリポジトリに `dots.mocr LICENSE AGREEMENT` があり、発効日の欄は August 8, 2025、権利者は Xingyin Information Technology (Shanghai) Co., Ltd. である。協定は「MIT License に従うことを条件に、次の条項にも拘束される」と書く。
- 協定が足しているものの例: モデル生成物の責任、著作物の無許可な電子化や大量収集の禁止（3.3(c)）、再配布時に協定の写しを渡すこと（7.1）、改変した重みには “Built with dots.mocr.” と出すこと（7.2）、準拠法と仲裁は中国・杭州（第 8 節）。API 経由で重みを配布しない利用は、協定の対象外で API 利用条件に従う（2.4）。
- 出典: https://github.com/studio-dots-ai/dots.mocr/blob/main/LICENSE と https://github.com/studio-dots-ai/dots.mocr/blob/main/dots.ocr%20LICENSE%20AGREEMENT （ファイル名は `dots.mocr LICENSE AGREEMENT`。中身の見出しが dots.mocr のまま dots.ocr 側にも置かれている）
- 出力は文書解析（README は SVG への変換も書く）。PDF 文字層とは書いていない。
- サイズは、Surya の README が dots.mocr を 3.0B と表に書いている。dots.mocr 自身のカード冒頭からは、この調査ではパラメータ数の文を取っていない。Surya 側の表は他社モデルの転記なので、3.0B は Surya README の主張としてだけ置く。
- 公式の単一 CLI は、この調査で読んだ README 冒頭には無かった。推論は別プロセスの Python / サーブになりうる。

### Chandra（Chandra OCR 2）

- 一次 URL: https://github.com/datalab-to/chandra
- リポジトリ作成は 2025-10-08。README の題は Chandra OCR 2。GitHub の最新リリースとして検索結果が示していた v0.2.0（2026-03-18）は、リリースノート本文をこの調査では開いていない。日付の一次出典は README の現在形と、リポジトリの作成日までにする。
- コードは Apache-2.0。重みは `MODEL_LICENSE` の modified OpenRAIL-M。https://github.com/datalab-to/chandra/blob/master/MODEL_LICENSE
- 重みの使用制限（Attachment 側の抜粋）: 前年の総売上が 200 万米ドルを超える主体、調達した出資または借入が 200 万米ドルを超える主体は、個人利用と研究を除いて使えない。Datalab の製品やサービスと競合する提供もできない。README は同じ趣旨を「研究、個人利用、資金調達または売上が 200 万ドル未満のスタートアップは無料」と要約している。Surya の README が書く 500 万ドルとは閾値が違う。Chandra は Chandra の MODEL_LICENSE を見る。
- 日本語: README は 90 以上の言語と、多言語ベンチの例に Japanese の画像を置く。https://github.com/datalab-to/chandra/blob/master/assets/examples/languages/japanese.png
- 出力は HTML / Markdown / JSON。PDF 文字層とは書いていない。
- 外部プロセスにできる。`chandra input.pdf ./output`。推奨は vLLM。Hugging Face 経路は torch が要る、と README が書く。
- Surya の比較表は Chandra OCR 2 を 4.0B と書く。Chandra README 自身のパラメータ数の文は、この調査では取っていない。4.0B は Surya README の表の値である。

### DeepSeek-OCR と DeepSeek-OCR-2

両方とも実在する。

- DeepSeek-OCR: https://github.com/deepseek-ai/DeepSeek-OCR 作成 2025-10-17。ライセンス MIT。README は 2025-10-20 の公開と、2025-10-23 の vLLM 対応を書く。モデルカードは `license: mit`、`language: multilingual`。日本語とは書いていない。https://huggingface.co/deepseek-ai/DeepSeek-OCR
- DeepSeek-OCR-2: https://github.com/deepseek-ai/DeepSeek-OCR-2 作成 2026-01-27。ライセンス Apache-2.0。README は 2026-01-27 の発表と、論文 arXiv:2601.20552 を書く。推論例は CUDA、bfloat16、flash attention で、プロンプトは Markdown への変換である。日本語とは書いていない。CPU 経路は、読んだ README 範囲には無かった。
- どちらも PDF 文字層とは書いていない。公式のインストール済みコマンド名は、読んだ README では Python スクリプトである。別プロセスにはできるが、`ocrmypdf` のような単一 CLI 契約は README に無い。
- パラメータ数は、この二つの README からは取っていない。

### GLM-OCR（2026）

- 一次 URL: https://github.com/zai-org/GLM-OCR 作成 2026-02-02。コードの GitHub license は Apache-2.0。
- 重みは MIT。モデルカードが `license: mit` と書き、言語に `ja` を含む。https://huggingface.co/zai-org/GLM-OCR
- README は、リポジトリのコードが Apache-2.0、GLM-OCR モデルが MIT、レイアウトの PP-DocLayout-V3 が Apache-2.0 で、両方に従うと書く。
- 0.9B。vLLM、SGLang、Ollama。Markdown 書き出しのスループットを README が測っている（単一レプリカ・単一並列で PDF 1.86 pages/s、画像 0.67 images/s、という著者測定）。
- PDF 文字層とは書いていない。2026-03-12 の更新は SDK と CLI（`pip install glmocr`）に触れている。外部プロセスにできる、と README のその文から読める。GPU メモリの下限は、この調査では取っていない。

### HunyuanOCR-1.5（2026）

- 一次 URL: https://github.com/Tencent-Hunyuan/HunyuanOCR
- 2026-07-07 に HunyuanOCR-1.5 を出した、と README が書く。論文 arXiv:2607.04884。1.0 の公開日は LICENSE が November 25, 2025 と書く。
- ライセンスは Tencent Hunyuan Community License Agreement。https://github.com/Tencent-Hunyuan/HunyuanOCR/blob/main/LICENSE
- LICENSE の冒頭は、この契約は EU、英国、韓国には適用されず、地域が限られると書く。SPDX の定型 OSI ライセンスではない。GitHub API は `NOASSERTION`。
- モデルカードの言語は `multilingual`、`en`、`zh`。日本語とは書いていない。https://huggingface.co/tencent/HunyuanOCR
- 出力は文書解析、文字位置、情報抽出、画像と文字の翻訳を一つの VLM で行う、と README が書く。PDF 文字層とは書いていない。Markdown という語は Hugging Face の README にある。
- 実行は vLLM と、llama.cpp による CPU / コンシューマ GPU / ラップトップ、と README が書く。パラメータ数は、読んだ README 範囲からは取っていない。
- 外部プロセス: 推論スクリプトと `llama-server`。単一の `hunyuanocr` コマンドを README が定義しているかは、読んだ範囲では未確認。

### LightOnOCR-3（2026）

- クライアントの一次 URL: https://github.com/lightonai/LightOnOCR 作成 2026-09-30。クライアントの LICENSE は Apache-2.0。README は、ベンチマークとモデルと上流コードは各自のライセンスのまま、と書く。
- モデルカード https://huggingface.co/lightonai/LightOnOCR-3-1B は `license: apache-2.0`。名前は LightOnOCR-3-1B。論文として arXiv:2601.14251 をカードがリンクする。
- 日本語は、カード冒頭とクライアント README からは確認していない。
- 出力: plain モードは Markdown（HTML の表、LaTeX、読み順）。grounding は LightOnOCR-3 だけで、ブロックのボックスを付ける、と README が書く。PDF 文字層とは書いていない。
- 外部プロセスにできる。`vllm serve lightonai/LightOnOCR-3-1B` と `lightonocr paper.pdf`。GPU 前提の vLLM である。CPU 所要時間は取っていない。

## 4. 2026 年に一次情報で確認した新しい名前

日付は各 README またはリポジトリの作成日。日本語「あり」は、その文書が日本語または `ja` を名指ししている場合だけである。

| 名前 | 文書上の日付 | コード | 重み | 日本語 |
| --- | --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | 2026-05-28 | Apache-2.0 | Apache-2.0（VL の LICENSE が Apache-2.0。1.6 専用の別 LICENSE は未確認で、系列のカードを見ている） | 系列は 109 言語。1.6 の文自体は日本語を名指ししていない |
| PP-OCRv6 | 2026-06-11 | Apache-2.0 | 同じリポジトリの Apache-2.0。個別モデルカードの差は未確認 | あり（中国語・英語・日本語） |
| HPD-Parsing | 2026-07-22 | Apache-2.0 の PaddleOCR リポジトリ内 | 未確認 | リリースノートは未記載 |
| DeepSeek-OCR-2 | 2026-01-27 | Apache-2.0 | Apache-2.0（リポジトリ license） | 未記載（多言語とも書いていない） |
| dots.mocr | 2026-03-19 | MIT の LICENSE に加え、別協定 | 同じ協定が重みを Model Materials に含める | カードは multilingual。日本語の名指しは未確認 |
| Chandra OCR 2 | README が現在の題。リポジトリは 2025-10-08 作成 | Apache-2.0 | modified OpenRAIL-M（売上・調達 200 万ドル、競合禁止） | あり（例画像と 90+ 言語） |
| GLM-OCR | リポジトリ 2026-02-02。技術報告の案内は 2026-03-12 | Apache-2.0 | MIT。レイアウト部品 PP-DocLayout-V3 は Apache-2.0 | あり（カードの `ja`） |
| HunyuanOCR-1.5 | 2026-07-07 | Community License（EU・英国・韓国は対象外） | 同じ契約 | カードは en / zh / multilingual。日本語の名指しは未確認 |
| Surya OCR 2 | README が現在の説明。citation の年は 2025 | Apache-2.0 | modified OpenRAIL-M（README は 500 万ドル未満） | あり（`ja`） |
| LightOnOCR-3-1B | クライアントリポジトリ 2026-09-30。論文番号は 2601 | クライアントは Apache-2.0 | モデルカードは apache-2.0 | 未記載 |

2025 年で、2026 年の後継が上にいるもの: PaddleOCR-VL（2025-10-16）、PP-OCRv5（2025 年の技術報告）、DeepSeek-OCR（2025-10-20、MIT）、olmOCR 2（2025-10-21、Apache-2.0、日本語の主張は無い）。

GOT-OCR2.0 は 2024-09-03 の公開で、ライセンス表示が衝突している。

## 5. このリポジトリの制約に直接触れる差

pdf2context は、OCR のあと `pdftotext` で本文を取る。文字が PDF の文字層に無いと、後段は空のままである。上の VLM の多くは Markdown か JSON を返すと書いており、元 PDF へ不可視文字層を戻すとは書いていない。文字層が要るなら、別途 PDF へ書き戻す処理が要る。その処理の有無は、各 README からは確認していない。

表と見出しを Markdown の構造として欲しい場合、README がそれを書くのは PaddleOCR、Surya、olmOCR、MinerU、Chandra、dots.mocr、GLM-OCR、LightOnOCR の plain モードである。Tesseract の文書は、表は苦手だと書いている。

ライセンスで Apache-2.0 の配布物へソースを混ぜる話と、別プロセスとして起動する話は別である。別プロセスの CLI が README にあるのは、Tesseract、OCRmyPDF、Surya、olmOCR、MinerU、Chandra、GLM-OCR（README が CLI と言う）、LightOnOCR である。EasyOCR と docTR と DeepSeek-OCR 系と GOT は、読んだ README の手順が Python API またはスクリプトである。
