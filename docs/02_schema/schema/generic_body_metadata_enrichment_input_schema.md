# generic_body_metadata_enrichment 入力スキーマ

## 関連リンク

- [汎用本文メタデータ・エンリッチメント設計](../generic_body_metadata_enrichment_design.md)
- [入力スキーマYAML正本](generic_body_metadata_enrichment_input_schema.yaml)
- [出力スキーマ解説](generic_body_metadata_enrichment_output_schema.md)
- [出力スキーマYAML正本](generic_body_metadata_enrichment_output_schema.yaml)
- [スキーマ索引](README.md)

## 目次

1. [概要](#1-概要)
2. [入力全体](#2-入力全体)
3. [パス](#3-パス)
4. [TDnetメタデータCSV](#4-tdnetメタデータcsv)
5. [`document_blocks.jsonl`](#5-document_blocksjsonl)
6. [`document_tables.jsonl`](#6-document_tablesjsonl)
7. [`processing_report.json`](#7-processing_reportjson)
8. [文書同定メタデータ](#8-文書同定メタデータ)
9. [文書突合](#9-文書突合)
10. [必須バリデーション](#10-必須バリデーション)
11. [明示的な非依存](#11-明示的な非依存)
12. [互換性変更](#12-互換性変更)

---

## 1. 概要

- コンポーネント: `generic_body_metadata_enrichment`
- スキーマ版: `1.0.0`
- 状態: `implemented`
- 機械可読な正本: `generic_body_metadata_enrichment_input_schema.yaml`
- 目的: 021側の汎用本文エンリッチメントが依存するTDnetメタデータとPDF前処理成果物を定義する

020のPythonコードには依存せず、既存PDF前処理成果物との互換性をファイル契約として定義する。

---

## 2. 入力全体

| アーティファクト | 必須 | 粒度 | 用途 |
|---|---:|---|---|
| 日次TDnetメタデータCSV | Yes | 1行=1開示 | 文書メタデータと処理対象 |
| `document_blocks.jsonl` | Yes | 1行=1本文ブロック | 分類と汎用根拠生成 |
| `processing_report.json` | Yes | 1ファイル=1文書 | 前処理状態・品質 |
| `normalized.md` | Conditional | 1ファイル=1文書 | 文書同定、監査、全文確認 |
| `evidence_package.json` | Conditional | 1ファイル=1文書 | `normalized.md` 欠損時の文書同定 |
| `document_tables.jsonl` | No | 1行=1表 | 表由来の補助シグナル |
| `candidate_evidence_spans.jsonl` | No / ignored | 1行=1候補根拠 | 不動産固有のため利用しない |

`normalized.md` と `evidence_package.json` は少なくとも一方を必要とする。

---

## 3. パス

### 3.1 メタデータ

```text
data/original/tdnet_metadata_{yyyymmdd}.csv
```

### 3.2 前処理成果物

```text
data/processed/tdnet_pdf_preprocessed/{yyyymmdd}/documents/{document_id}/
  normalized.md
  document_blocks.jsonl
  document_tables.jsonl
  processing_report.json
  evidence_package.json
  candidate_evidence_spans.jsonl
```

入力ルートは設定で変更可能とする。021の実行から020リポジトリへ書き込んではならない。

---

## 4. TDnetメタデータCSV

### 4.1 必須列

| 列 | 型 | Nullable | 説明 |
|---|---|---:|---|
| `disclosure_date` | date string | No | `YYYY-MM-DD` または `YYYYMMDD` |
| `code` | string | No | 証券コード。`issuer_code` をaliasとして許容 |
| `company_name` | string | No | 発行体名。`issuer_name` をaliasとして許容 |
| `title` | string | No | 開示タイトル原文 |
| `document_url` | URI string | No | 開示PDF URL |

### 4.2 推奨・任意列

| 列 | 型 | Nullable | 説明 |
|---|---|---:|---|
| `disclosure_number` | string | Yes | 推奨source ID |
| `disclosure_time` | time string | Yes | 開示時刻 |
| `disclosure_datetime` | datetime string | Yes | 開示日時 |
| `xbrl_url` | URI string | Yes | XBRL URL |
| `has_xbrl` | boolean | Yes | XBRL有無 |
| `market` | string | Yes | 市場区分 |
| `update_history` | string | Yes | 更新・訂正情報 |
| `list_page` | integer | Yes | TDnet一覧ページ番号 |
| `source_url` | URI string | Yes | 一覧ページURL |
| `fetched_at_utc` | UTC datetime | Yes | 取得日時 |
| `document_id` | string | Yes | 前処理文書への直接キー |

`source_id` は `disclosure_number`、なければ `document_url` を使う。

### 4.3 日付整合

ファイル名の `{yyyymmdd}` と各行の `disclosure_date` は一致しなければならない。不一致行は別日の処理へ暗黙移動せず、`invalid_disclosure_date` として失敗させる。

---

## 5. `document_blocks.jsonl`

1行1本文ブロック。

| フィールド | 型 | Nullable | 制約・用途 |
|---|---|---:|---|
| `block_id` | string | No | 主キー |
| `document_id` | string | No | 親文書ID |
| `page_number` | integer | No | 1以上 |
| `page_layout_type` | enum | No | レイアウト種別 |
| `block_order` | integer | No | ページ内順序、1以上 |
| `block_type` | enum | No | 見出し、本文、注記等 |
| `text` | string | No | 空文字不可、原文根拠 |
| `normalized_text` | string | Yes | 前処理側正規化値 |
| `char_count` | integer | Yes | 0以上 |
| `bbox` | number[4] | Yes | 座標 |
| `extraction_method` | string | Yes | 抽出方式 |
| `quality_score` | float | Yes | 0.0〜1.0 |

### 5.1 `page_layout_type`

```text
doc_like
slide_like
table_heavy
scanned_or_image
mixed
```

### 5.2 `block_type`

```text
document_title
page_title
slide_title
section_heading
heading
paragraph
bullet
table
note
footer
header
unknown
```

旧形式との互換のため `heading` を許容する。`header` と `footer` は既定で分類根拠から除外する。

---

## 6. `document_tables.jsonl`

1行1表。ファイル自体は任意で、欠損時も処理を継続する。

| フィールド | 型 | Nullable | 制約・用途 |
|---|---|---:|---|
| `table_id` | string | No | 主キー |
| `document_id` | string | No | 親文書ID |
| `page_number` | integer | No | 1以上 |
| `page_layout_type` | enum | Yes | ページレイアウト |
| `table_order` | integer | No | ページ内順序 |
| `markdown_table` | string | Yes | 分類・根拠用文字列 |
| `raw_cells_json` | string[][] | Yes | 生セル |
| `extraction_method` | string | Yes | 抽出方式 |
| `quality_score` | float | Yes | 0.0〜1.0 |

表欠損時は `missing_optional_tables` warningを記録する。本文ブロックが空の場合は処理を継続しない。

---

## 7. `processing_report.json`

### 7.1 必須

| フィールド | 型 | 許容値 |
|---|---|---|
| `document_id` | string | 文書ディレクトリIDと一致 |
| `processing_status` | enum | `success`, `success_with_warnings`, `failed` |
| `document_text_extraction_quality` | enum | `high`, `medium`, `low` |

### 7.2 任意

`source_pdf_path`, `sha256_hash`, `page_count`, `pdf_layout_type`, `page_layout_summary`, `text_char_count`, `block_count`, `table_count`, `evidence_span_count`, `used_ocr`, `used_vision`, `errors`

`processing_status=failed` はenrichment失敗とする。`success_with_warnings` は処理を継続し、`preprocessing_success_with_warnings` を出力の `warning_codes` に追加する。qualityが`low`の場合は処理可能でも `candidate_stage=needs_review` とする。

---

## 8. 文書同定メタデータ

`normalized.md` front matter、または `evidence_package.json.document_metadata` から以下を取得する。

| フィールド | 必須 |
|---|---:|
| `document_id` | Yes |
| `issuer_code` | Yes |
| `disclosure_date` | Yes |
| `title` | Yes |
| `source_id` | No |
| `issuer_name` | No |
| `pdf_layout_type` | No |
| `page_count` | No |

両方存在する場合は軽量な `normalized.md` front matterをindex構築に用い、実処理時に必要ならJSONを読む。

---

## 9. 文書突合

以下の順に完全一致する候補を探す。

1. `document_id`
2. `source_id`（`disclosure_number`、なければ `document_url`）
3. `disclosure_date + issuer_code + normalized_title`

タイトル照合ではNFKC、大小文字、全角空白、連続空白、照合用記号を正規化する。保存する原文は変更しない。

候補0件:

```text
preprocessed_document_not_found
```

候補複数:

```text
ambiguous_preprocessed_document
```

複数候補をevidence件数などで推測選択しない。

---

## 10. 必須バリデーション

- メタデータ必須列が存在する
- `disclosure_number` または `document_url` が得られる
- 日次ファイルと開示日が一致する
- 文書同定メタデータが得られる
- `document_blocks.jsonl` と `processing_report.json` が存在する
- 本文ブロックが1件以上ある
- 全成果物の `document_id` が一致する
- `processing_status` が `success` または `success_with_warnings`
- page/orderが1以上
- quality scoreが0.0〜1.0

warning:

- `document_tables.jsonl` 欠損
- `document_text_extraction_quality=low`
- 一部任意フィールド欠損

---

## 11. 明示的な非依存

`candidate_evidence_spans.jsonl` は、既存不動産キーワードで生成されるため、本工程の分類、confidence、根拠、routingに使用しない。

汎用根拠は `document_blocks.jsonl` と `document_tables.jsonl` から生成する。この方針により、020側の不動産語彙変更と021側の汎用分類を分離する。

---

## 12. 互換性変更

- 必須ファイル・必須列の追加: major
- 任意フィールドの追加: minor
- 説明・例の修正: patch

020側の前処理出力が変更された場合は、この入力スキーマへの適合を確認してから021側で利用する。
