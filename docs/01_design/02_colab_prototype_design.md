# 詳細設計：Colab検証環境（前処理＋マクロテーマ付与）

**版**: v0.1（2026年9月7日）
**上位文書**: [マクロテーマ付与パイプライン](01_macro_theme_tagging_pipeline.md)
**位置づけ**: 01の設計をColab上で試行錯誤するための実装設計。GCPは使わない。01と矛盾する場合は01が優先する。

---

## 目次

1. [目的とスコープ](#1-目的とスコープ)
2. [実行環境とDriveレイアウト](#2-実行環境とdriveレイアウト)
3. [全体フロー](#3-全体フロー)
4. [preprocess_disclosures.py](#4-preprocess_disclosurespy)
5. [tag_macro_theme.py](#5-tag_macro_themepy)
6. [Gemmaの選定と読み込み](#6-gemmaの選定と読み込み)
7. [プロンプト設計](#7-プロンプト設計)
8. [処理量とスループット](#8-処理量とスループット)
9. [受入基準](#9-受入基準)
10. [既存コードからの変更点](#10-既存コードからの変更点)

---

## 1. 目的とスコープ

**過去1か月の適時開示に対して、Colab上でマクロテーマ付与を試行し、分類体系が機能するかを測る。**

- クラウドLLM APIを使わず、Drive上のGemmaでローカル推論する。
- GCS・BigQuery・Terraform・Cloud Runは使わない。出力はDrive上のJSONLとする。
- **試行錯誤が目的である。** プロンプト・モデルサイズ・スパン抽出条件を何度も変えて回すことを前提に設計する。

**作るもの**

| ファイル | 役割 |
|---|---|
| `notebook/preprocess_disclosures.py` | PDF → 1文書1レコードのJSONL |
| `notebook/tag_macro_theme.py` | 前処理JSONL → マクロテーマ付与JSONL |

## 2. 実行環境とDriveレイアウト

- **Colab無料枠（T4・VRAM 16GB）を前提とする。** T4はTuring世代であり、次の制約がある。
  - **bfloat16に非対応。** `torch_dtype=torch.float16` を使う。bf16を指定すると動作しないか極端に遅くなる。
  - **Flash Attention 2に非対応**（Ampere以降が必要）。`sdpa` または `eager` を使う。
  - 無料枠はGPU割当に上限があり、長時間の連続実行で制限がかかる。**1回の実行を1〜2時間に収める設計が要る**（8章）。
- 既存の `notebook/*.py` はColabで動作実績があるため、その前提（`_ensure_dependency()` による実行時pip、`ROOT_DIR` 定数）を**維持する**。01の設計にある「依存を requirements.txt で解決」はGCP移行時の話であり、本環境には適用しない。

**ルートは既存コードに合わせる。** `notebook/fetch_tdnet_metadata.py` と `notebook/tdnet_pdf_preprocessing.py` がいずれも `ROOT_DIR = "/content/drive/MyDrive/git/prop_candidates/"` を使っており、PDFも実際にこの配下に取得済みである。**新しいルートを作らず、既存のパスを正とする。**

```text
/content/drive/MyDrive/git/prop_candidates/
├── models/                                   ← 本設計で追加
│   ├── gemma-4-12b-it-Q4_K_M.gguf
│   └── gemma-4-E4B-it-Q4_K_M.gguf
├── data/
│   ├── master/                               ← リポジトリからコピー
│   │   ├── dim_macro_theme_seed.csv          L1/L2統合・101行
│   │   ├── dim_company_seed.csv
│   │   └── jpx_listed_202606.xls
│   ├── original/
│   │   └── tdnet_metadata_{yyyymmdd}.csv     ← 取得済み
│   ├── raw/tdnet_pdfs/{yyyymmdd}/*.pdf       ← 取得済み
│   ├── samples/                              ← 本設計で追加
│   │   ├── stratified_sample_300.jsonl
│   │   └── stratified_sample_300_summary.csv
│   ├── processed/
│   │   └── disclosures_{yyyymmdd}.jsonl      preprocess の出力
│   └── product/
│       └── macro_themes_{yyyymmdd}.jsonl     tag の出力
└── logs/
    └── run_{timestamp}.json
```

- PDFの実配置は `data/raw/tdnet_pdfs/{yyyymmdd}/` である。`fetch_tdnet_metadata.py` の出力先に従う。
- マスタCSVはリポジトリから `data/master/` へコピーして使う。

- **モデルはDriveに置くが、実行前に `/content` へコピーする。** DriveのI/Oは低速（20〜50MB/s）で、推論中に読み続けると著しく遅い。12Bの4bit量子化で約8GB、コピーに3〜7分かかるがセッション中は一度で済む。
- 検証用の入力として `data/samples/tdnet_bodies_202608.jsonl`（本文236件）をリポジトリから持ち込めば、**PDF取得を省略して即座にタグ付けの試行に入れる。**

## 3. 全体フロー

```
[取得]  notebook/fetch_tdnet_metadata.py（既存・変更なし）
          → tdnet_metadata_{yyyymmdd}.csv + PDF
             ↓
[前処理] notebook/preprocess_disclosures.py（新規）
          → disclosures_{yyyymmdd}.jsonl   1文書1行
             ↓
[付与]   notebook/tag_macro_theme.py（新規）
          → macro_themes_{yyyymmdd}.jsonl  1テーマ言及1行
```

- 3工程を独立させる。**付与だけを何度も回せることが最重要**である。プロンプトやモデルを変えるたびにPDF取得と前処理をやり直すのは非現実的である。

## 4. preprocess_disclosures.py

`notebook/tdnet_pdf_preprocessing.py` を参考にするが、**出力を大幅に簡素化する。**

### 4.1 現行の出力と、その問題

現行は1文書あたり6ファイルを出力する。

```
{document_id}/normalized.md
{document_id}/document_blocks.jsonl
{document_id}/document_tables.jsonl
{document_id}/candidate_evidence_spans.jsonl
{document_id}/evidence_package.json
{document_id}/processing_report.json
```

236文書で1,416ファイルになる。**Drive上では小さいファイルの大量生成が極端に遅い。** また後段が6ファイルを突合する必要があり、試行のたびに整合を気にすることになる。

### 4.2 簡素化した出力

**1文書1行のJSONL、1日1ファイル。**

```json
{
  "document_id": "20260831_6310_a1b2c3d4",
  "disclosure_date": "2026-08-31",
  "code": "6310",
  "company_name": "井関農機",
  "title": "固定資産の譲渡および特別利益の計上に関するお知らせ",
  "source_type": "timely_disclosure",
  "document_url": "https://...",
  "pdf_sha256": "...",
  "page_count": 2,
  "char_count": 1843,
  "pdf_layout_type": "text",
  "text": "全文（正規化済み）",
  "blocks": [
    {"i": 0, "page": 1, "text": "...", "type": "heading"},
    {"i": 1, "page": 1, "text": "...", "type": "paragraph"}
  ],
  "status": "ok",
  "error": null
}
```

- **`blocks` を残す理由は、スパン抽出に必要だから**である。テーマ語の出現位置から前後ブロックを取る処理（5.2）が、本文の平文だけでは書けない。ただし現行の `block_id` / `quality_score` / `normalized_text` などは落とし、`i` / `page` / `text` / `type` の4項目に絞る。
- `document_tables` は**別配列にせず、`blocks` に `type: "table"` として混ぜる**。テーブルはMarkdown文字列として `text` に入れる。順序が保たれるため、前後ブロックの取得が単純になる。
- `candidate_evidence_spans` は**前処理では作らない。** スパンの切り出し条件（キーワード、前後幅）は試行錯誤の対象であり、前処理で固定すると毎回PDFから作り直すことになる。付与側で都度生成する。
- `evidence_package.json` と `processing_report.json` は廃止し、必要な項目（`status` / `error` / `pdf_layout_type` / `pdf_sha256`）を本体に統合する。

### 4.3 引き継ぐ処理

以下は現行の実装をそのまま使う。**動作実績があるため、ロジックは変更しない。**

- PyMuPDFによるブロック抽出と、pdfplumberによるテーブル抽出
- ページレイアウト判定（`SCAN_TEXT_CHAR_THRESHOLD` / `SCAN_IMAGE_AREA_THRESHOLD`）とスキャンPDFの検出
- ヘッダ・フッタの繰り返し検出と除去
- 文字列正規化（`_normalize_text` / `_normalize_for_match`）

### 4.4 追加する処理

- **暗号化PDFの復号。** `cryptography` を依存に追加する。TDnetにはAES暗号化PDFが混じり、これがないとテキスト抽出が失敗する。
- **`source_type` の判定。** タイトルの正規表現で `timely_disclosure` / `earnings` / `earnings_presentation` / `forecast_revision` を付与する。
- スキャンPDF（`pdf_layout_type = "scan"`）は `status = "skipped_scan"` として本文を空にする。OCRは行わない。

## 5. tag_macro_theme.py

### 5.1 処理の流れ

```
disclosures_{yyyymmdd}.jsonl
    ↓
[1] ゲート：マスタ語彙239語で本文を照合
    ↓  1語も無い → themes=[] で確定、LLMを呼ばない
[2] 候補L1の絞り込み：ヒットした語が属するL1のみを候補とする
    ↓
[3] スパン抽出：ヒット語を含むブロック±1を連結、重複排除
    ↓
[4] LLM：候補L1とそのL2、スパンのみを渡して判定
    ↓
[5] 検証：コードがマスタに存在するか、evidenceが原文に含まれるか
    ↓
macro_themes_{yyyymmdd}.jsonl
```

### 5.2 スパン抽出

**小型モデルで成立させるための核となる工夫である。**

- 決算短信の平均は13,855字、決算説明資料は11,703字ある。全文を投げると、プロンプトが長すぎて小型モデルの精度が落ち、速度も出ない。
- ヒット語を含むブロックとその前後1ブロックを連結してスパンとする。既存 `tdnet_pdf_preprocessing.py` の `EVIDENCE_CONTEXT_WINDOW` と同じ考え方であり、**キーワード配列を不動産用からマクロテーマ語彙に差し替えるだけで流用できる。**
- 1スパンの上限を1,200字、1文書あたりのスパン合計を4,000字で打ち切る。超過分は出現頻度の高いL1のスパンを優先する。
- スパンは重複排除する（同一ブロックが複数語でヒットする場合が多い）。

### 5.3 候補L1の絞り込み

- ゲートでヒットした語が属するL1のみをプロンプトに載せる。
- 実測では1文書あたり平均3.2個のL1がヒットする。**16テーマ全部を載せる必要はない。**
- プロンプトに載せる分類定義が16テーマ分（約4,000トークン）から3テーマ分（約800トークン）に減る。
- **候補外のテーマは付与できなくなる**が、これは意図した制約である。語彙に無い表現でテーマを当てることは、そもそもゲートを通過しない。語彙不足はゲートの改善で対処する。

### 5.4 出力

**1テーマ言及1行のJSONL。**

```json
{
  "theme_mention_id": "a1b2c3d4e5f6a7b8",
  "document_id": "20260831_6310_a1b2c3d4",
  "disclosure_date": "2026-08-31",
  "code": "6310",
  "source_type": "timely_disclosure",
  "theme_code": "commodity_price",
  "subtheme_code": "grain",
  "direction": "up",
  "evidence_text": "原材料である小麦の価格が高騰しており",
  "extraction_confidence": 0.9,
  "gate_hit_terms": ["小麦", "原材料"],
  "model": "gemma-3-12b-it-q4",
  "prompt_version": "v1",
  "taxonomy_version": "2026-09-07"
}
```

- テーマが付かなかった文書も `theme_code: null` で1行出す。**「付かなかった」と「処理していない」を区別するため**である。
- `theme_mention_id` は `SHA256(document_id + theme_code + subtheme_code + evidence_text)` の先頭16桁。再実行で同じIDが再現する。
- `prompt_version` と `model` を必ず記録する。**試行錯誤の比較にはこれが要る。**

## 6. モデルの選定と実行方式

### 6.1 Gemma 4 を使う

Gemma 4 は2026年4月2日リリース。**ライセンスがApache 2.0になり**、Gemma 3までの独自ライセンスにあった制約が外れている。将来クラウドで自前ホストする際にも制限がない。140言語で事前学習し、35言語以上を公式サポート、日本語を含む。

| 変種 | パラメータ | 4bit時の目安 | T4(16GB) | 評価 |
|---|---|---|---|---|
| E2B | 2.3B（実効） | 約2GB | 余裕 | 小さすぎる |
| **E4B** | 4.5B（実効） | 約4GB | 余裕 | **速度側の比較対象** |
| **12B Unified** | 11.95B | 約7GB | 余裕 | **本命** |
| 26B A4B（MoE） | 25.2B中 活性3.8B | 約14GB | **入らない** | T4では見送り |
| 31B Dense | 30.7B | 約17GB | 入らない | 見送り |

- **本命は 12B、比較対象は E4B。** 両者を同じスパン・同じプロンプトで回し、一致率を見る（9章）。
- **26B A4B は魅力的だが T4 では採用しない。** 活性3.8BのMoEで推論は速いが、重みは25.2B分をVRAMに載せる必要があり、4bitでも約14GB。KVキャッシュを加えると16GBに収まらない。L4（24GB）以上が使えるようになった時点で再検討する。

### 6.2 実行方式は llama.cpp を使う

**transformers + bitsandbytes ではなく、llama.cpp（GGUF）を使う。** llama.cpp は Gemma 4 をリリース当日からサポートしている。

判断根拠は3点ある。

1. **GBNF文法によるJSON制約が使える。** これが決定的である。Gemma にはネイティブのstructured output機能がなく、transformers経由だと「生成→パース→失敗したら再生成」という不確実な手順になる。GBNF文法を与えれば、**構文的に妥当なJSONしか生成されない。** パース失敗率がゼロになる。
2. **量子化済みGGUFをそのまま置ける。** Gemma 4 12B のfp16重みは約24GBあり、Google Drive無料枠（15GB）に入らない。Q4_K_M のGGUFなら約7GBで収まる。
3. 単一ストリーム生成では transformers+bnb より速い。

**量子化は `Q4_K_M` を基本とする。** Unsloth の UD-Q4_K_XL のような改良版があればそちらを優先する。手製の Q4_0 変換は精度が落ちるため使わない。

### 6.3 モデルの配置と読み込み

```
Drive(models/gemma-4-12b-it-Q4_K_M.gguf, 約7GB)
   → /content へコピー（3〜7分）
   → llama-cpp-python で読み込み、n_gpu_layers=-1 で全層GPUへ
```

- **Driveから直接読まない。** DriveのI/Oは20〜50MB/sで、推論中に読み続けると律速する。`/content` へコピーしてから使う。
- **Driveは企業版2TBのため容量制約はない。** 制約は T4 の VRAM 16GB のみである。これにより次が可能になる。
  - **量子化水準を並べて比較できる。** Q4_K_M / Q5_K_M / Q8_0 を同時に置き、精度と速度のトレードオフを実測する。12BのQ8_0は約13GBでT4にぎりぎり載る。**量子化による精度劣化は、分類タスクでは無視できない可能性があり、検証項目に含める価値がある。**
  - **26B A4B を先に置いておける。** T4では動かないが、L4以上が使えるようになった時点で即座に試せる。
  - **試行ごとの出力を全世代残せる。** プロンプト版ごとの結果を消さずに保持し、後から突き合わせられる。これが `prompt_version` を出力に記録する設計（5.4）と噛み合う。

### 6.4 出力の構造化

GBNF文法でスキーマを強制する。概略は次のとおり。

```gbnf
root   ::= "{" ws "\"themes\"" ws ":" ws themes ws "}"
themes ::= "[" ws (theme (ws "," ws theme)*)? ws "]"
theme  ::= "{" ws "\"theme_code\"" ws ":" ws l1code ws ","
                ws "\"subtheme_code\"" ws ":" ws (l2code | "null") ws ","
                ws "\"direction\"" ws ":" ws direction ws ","
                ws "\"evidence_text\"" ws ":" ws string ws "}"
l1code    ::= "\"commodity_price\"" | "\"import_price\"" | ...
direction ::= "\"up\"" | "\"down\"" | "\"neutral\"" | "\"unknown\""
```

- **`l1code` と `l2code` の選択肢は、候補L1に応じて実行時に生成する**（5.3）。マスタCSVから動的に組み立てる。
- これにより「マスタに存在しないコードを返す」という失敗が構造的に起きなくなる。後段の検証はコードの妥当性ではなく、**evidenceが原文に含まれるか**の確認に集中できる。
- 文法で防げないのは意味の誤りだけである。そこはプロンプトと目視確認で見る。

## 7. プロンプト設計

### 7.1 構成

```
[役割] 日本企業の適時開示から、外部環境（マクロ）要因を抽出する
[定義] 候補L1テーマの定義・includes・excludes（3テーマ程度）
[定義] 候補L1配下のL2一覧
[禁止] 企業への影響・企業アクションをテーマにしない
[入力] スパン（最大4,000字）
[出力] JSON形式の指定 + few-shot 1件
```

- **`excludes` を必ず含める。** 判定が揺れるのは境界例であり、これがないと `commodity_price` と `import_price` を区別できない。
- **レイヤー混同の禁止を明示する。** 「原材料コスト上昇」（企業への影響）や「値上げ」（企業アクション）をテーマに入れさせない。
- 日本語で書く。Gemmaは多言語対応だが、対象文書が日本語であり、指示と定義を同一言語に揃えたほうが安定する。

### 7.2 バージョン管理

- プロンプトは `notebook/prompts/macro_theme_v1.txt` としてファイルに置き、`prompt_version` を出力に記録する。
- **プロンプトをコード内の文字列リテラルにしない。** 試行錯誤のたびにdiffが読めなくなる。

## 8. 処理量とスループット

### 8.1 日次運用が基本、層化サンプルは試行用

**本番の運用形態は「毎日、その日の全開示にタグを付ける」である。** 層化サンプルはプロンプトとモデルを試行錯誤するためのテストフィクスチャであり、運用モードではない。

PDFは過去30日の全開示（約9,400件・約4.7GB）が取得済みである。1営業日あたり約426件になる。

| 実行形態 | 件数 | 前処理 | 推論（12B） | 推論（E4B） |
|---|---|---|---|---|
| **日次（1日分）** | **426** | **27分** | **1.8時間** | **0.6時間** |
| 層化サンプル（試行用） | 300 | 20分 | 1.3時間 | 0.4時間 |
| バックフィル（30日分） | 9,372 | 9.8時間 | 40.0時間 | 12.8時間 |

**日次は成立する。** 1日分なら12Bでも1.8時間であり、Colabのセッション内に収まる。

**バックフィルは成立しない。** 30日分を12Bで流すと40時間かかる。これは初期投入時の一度きりの作業であり、かつ**プロンプトやマスタを変更するたびに再実行が必要になる**。試行錯誤の段階でこれを回してはならない。

### 8.2 試行と運用でモードを分ける

| モード | 対象 | 用途 |
|---|---|---|
| `--sample` | 層化サンプル300件（固定） | プロンプト・モデル・スパン条件の試行 |
| `--date YYYY-MM-DD` | 指定日の全開示 | 日次運用 |
| `--from/--to` | 期間の全開示 | バックフィル |

- **試行は必ず `--sample` で行う。** 同一サンプルを使い続けることで、プロンプト版・モデル間の比較が成立する。サンプルが変わると比較にならない。
- 層化サンプルのIDリストは `data/samples/` に保存し、**試行間で固定する**。
- 層化の設計は次のとおり。17業種区分から各15〜20件、`source_type` は実比率（`timely_disclosure` 49.3% / `earnings` 31.3% / `earnings_presentation` 13.1% / `forecast_revision` 6.3%）に合わせる。**ゲート通過を抽出条件にしない**（ゲートの誤検出と取りこぼしの両方を測るため）。
- 食品100社に絞ったサンプルは使わない。分類体系の検証が目的である以上、食品だけでは `tech_investment_cycle`（実測8件）、`trade_policy`（10件）、`asset_price`（1件）が検証できない。半導体・電機がなければ技術サイクルは、不動産がなければ資産価格は出現しない。

### 8.3 無料枠での日次運用は上限に近い

- 前処理27分＋推論1.8時間で、**1日あたり約2.3時間**のGPU使用となる。Colab無料枠のGPU割当は日によって変動し、**これを毎日続けるのは上限に抵触する可能性が高い。**
- 対策は3つあり、検証結果を見て選ぶ。
  1. **E4Bを日次運用に使う。** 0.6時間で済み、前処理を含めても約1.1時間に収まる。12Bは層化サンプルでの品質基準として使い、E4Bとの一致率で妥当性を担保する（9章）。
  2. Colab Proに切り替える。
  3. 日次のタグ付けをGCP側（01の設計）へ移す。Colabは試行専用とする。
- **したがってE4Bと12Bの比較は、「E4Bで足りるか」ではなく「日次運用をE4Bで回せるか」という問いである。** 品質が同等なら、速度3倍のE4Bが運用上の第一候補になる。

### 8.4 想定処理量（層化サンプル300件の場合）

| ステージ | 件数 | 想定時間 |
|---|---|---|
| PDF取得 | — | 取得済み |
| 前処理 | 300 | 約20分 |
| ゲート | 300 | 数秒 |
| LLM付与 | 約190件（ゲート通過分） | **12Bで80〜95分** |

- 12BのQ4_K_M・T4で15〜25 tok/s。プロンプト約2,000トークン、出力約200トークンとして1件20〜30秒。
- E4Bなら3倍程度速く、30分前後で完走する見込みである。

### 8.5 セッション断への対応

**Colabのセッションは切れる。** 無料枠では特に頻繁である。

- **1件処理するごとに追記保存する。** 全件終了後にまとめて書き出す設計にしてはならない。
- 起動時に出力JSONLを読み、`document_id` が既に存在する文書はスキップする。**再開可能であることを必須要件とする。**
- ログに進捗（処理済み件数・経過時間・推定残り時間）を出す。

## 9. 受入基準

- 過去1か月236件に対して、前処理と付与が完走すること。セッション断があっても再開して完了できること。
- 以下が数値で出ること。**これが本設計の目的である。**

| 指標 | 見方 |
|---|---|
| ゲート通過率（`source_type` 別） | 実測の34.5%/50.0%/95.9%/92.6%と整合するか |
| テーマ付与率（ゲート通過分のうち実際にテーマが付いた割合） | ゲートの誤検出率を示す |
| L1別の付与件数 | 全く付かないテーマは定義かゲート語彙の問題 |
| L2 null率（L1別） | 高いテーマはL2定義の不足 |
| `other` 率 | 高ければ分類体系の欠落 |
| GBNF適用下でのスキーマ違反 | 原則ゼロのはず。発生するなら文法定義の誤り |
| E4Bと12Bの一致率 | **日次運用をE4Bで回せるかの判断材料**（8.3）。速度差は約3倍 |
| 量子化水準（Q4_K_M / Q8_0）の一致率 | 量子化による精度劣化の有無。差がなければQ4で確定 |
| 1件あたり処理時間 | 全市場9,400件へ拡張した場合の見積り根拠 |

**目視確認も行う。** 付与結果から各L1につき3件ずつ抽出し、`evidence_text` が本当にそのテーマを述べているかを人が読む。**数値だけでは誤分類の質が分からない。**

## 10. 既存コードからの変更点

| 項目 | 現行 | 本設計 |
|---|---|---|
| 出力ファイル数 | 1文書6ファイル | 1日1ファイル（JSONL） |
| ブロック情報 | `block_id` / `quality_score` / `normalized_text` 等 | `i` / `page` / `text` / `type` の4項目 |
| テーブル | 別ファイル・別配列 | `blocks` に `type: "table"` で混在 |
| evidence span | 前処理で生成し保存 | 付与側で都度生成（試行対象のため） |
| キーワード | 不動産取引用22語 | マクロテーマ語彙239語（マスタから読み込み） |
| 暗号化PDF | 未対応 | `cryptography` で復号 |
| `source_type` | なし | タイトルの正規表現で判定 |
| 推論方式 | — | llama.cpp（GGUF）＋GBNF文法制約 |

**現行の処理ロジック（PDF解析・レイアウト判定・正規化）は変更しない。** 動作実績のある部分に手を入れると、検証したいこと（分類体系が機能するか）と、壊れた原因の切り分けができなくなる。
