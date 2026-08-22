# generic_body_metadata_enrichment 出力スキーマ

## 関連リンク

- [汎用本文メタデータ・エンリッチメント設計](../generic_body_metadata_enrichment_design.md)
- [入力スキーマ解説](generic_body_metadata_enrichment_input_schema.md)
- [入力スキーマYAML正本](generic_body_metadata_enrichment_input_schema.yaml)
- [出力スキーマYAML正本](generic_body_metadata_enrichment_output_schema.yaml)
- [スキーマ索引](README.md)

## 目次

1. [概要](#1-概要)
2. [出力成果物](#2-出力成果物)
3. [主テーブル](#3-主テーブル)
4. [enum](#4-enum)
5. [文書詳細JSON](#5-文書詳細json)
6. [summary](#6-summary)
7. [failed](#7-failed)
8. [report](#8-report)
9. [バリデーションルール](#9-バリデーションルール)
10. [versioning](#10-versioning)
11. [ETLノート](#11-etlノート)

---

## 1. 概要

- コンポーネント: `generic_body_metadata_enrichment`
- スキーマ版: `1.0.0`
- 状態: `implemented`
- 機械可読な正本: `generic_body_metadata_enrichment_output_schema.yaml`
- 出力ルート: `data/processed/tdnet_generic_body_metadata_enriched/`
- 粒度: 1行 = 1開示文書

本出力は、用途固有のイベント抽出より前に置く文書単位の中間データである。マクロテーマ、顧客 relevance、企業・製品・地域・金額の詳細抽出は含めない。

---

## 2. 出力成果物

| アーティファクト | 形式 | パス | 粒度 |
|---|---|---|---|
| 文書詳細 | JSON | `{yyyymmdd}/documents/{document_id}/generic_body_metadata_enrichment.json` | 1ファイル=1文書 |
| 日次主出力 | CSV | `{yyyymmdd}/generic_body_enriched_disclosure_metadata.csv` | 1行=1文書 |
| 日次summary | CSV | `{yyyymmdd}/enrichment_summary.csv` | 1行=1入力文書 |
| 日次failed | CSV | `{yyyymmdd}/enrichment_failed.csv` | 1行=1失敗 |
| 日次report | JSON | `{yyyymmdd}/daily_enrichment_report.json` | 1ファイル=1日 |
| 実行主出力 | CSV | `generic_body_enriched_disclosure_metadata_all.csv` | 1行=1処理文書 |
| 実行summary | CSV | `enrichment_summary_all.csv` | 1行=1入力文書 |
| 実行failed | CSV | `enrichment_failed_all.csv` | 1行=1失敗 |
| 実行report | JSON | `enrichment_report_all.json` | 1ファイル=1実行 |

CSVは `utf-8-sig` とする。JSONはUTF-8、非ASCII文字を保持する。

---

## 3. 主テーブル

テーブル名:

```text
tdnet_generic_body_enriched_disclosure_metadata
```

主キー:

```text
document_id
```

実行時例外で分類できなかった文書は主テーブルへ出さず、summaryとfailedへ記録する。スキーマ検証まで実行できた文書は、`failed_validation` でも主テーブルへ残す。

文書詳細JSONを正本とし、主CSVは同じ文書payloadから決定的に生成する検索・結合・BI向けprojectionとする。CSVとJSONに対して分類ロジックを別々に実行しない。

### 3.1 プロベナンスと原本メタデータ

| カラム | 型 | Nullable | 説明 |
|---|---|---:|---|
| `schema_version` | string | No | 出力契約版 |
| `enrichment_version` | string | No | ルール実装版 |
| `enrichment_method` | string | No | `rule_based` |
| `document_id` | string | No | 主キー |
| `source_id` | string | No | disclosure number、なければURL |
| `disclosure_date` | date string | No | 開示日 |
| `disclosure_time` | time string | Yes | 開示時刻 |
| `issuer_code` | string | No | 証券コード |
| `issuer_name` | string | No | 発行体名 |
| `title` | string | No | 開示タイトル |
| `document_url` | URI string | No | 原本URL |
| `generated_at_utc` | UTC datetime | No | 生成日時 |

### 3.2 分類

| カラム | 型 | Nullable | 説明 |
|---|---|---:|---|
| `status` | enum | No | `success`, `needs_review`, `failed_validation` |
| `document_type` | enum | No | primary開示種別 |
| `topic_tags` | JSON array string | No | 複数の主要トピック |
| `business_event_types` | JSON array string | No | 事業イベント候補 |
| `financial_impact_types` | JSON array string | No | 財務影響候補 |
| `impact_direction` | enum | No | 事業・業績への方向 |
| `actual_or_forecast` | enum | No | 実績・予想区分 |
| `time_horizon` | enum | No | 影響時間軸 |
| `quantitative_data_present` | boolean | No | 数値記載有無 |
| `body_confidence` | float | No | 0.0〜1.0のルール充足度 |
| `classification_reason` | string | No | 判定理由 |

JSON array stringは空の場合でも `[]` とし、nullや空文字にしない。

`document_type_candidates` の全候補とscoreはCSVへ出さず、詳細JSONの `classification.document_type_candidates` にのみ保持する。

### 3.3 根拠、品質、routing

| カラム | 型 | Nullable | 説明 |
|---|---|---:|---|
| `evidence_ids` | JSON array string | No | CSVでは最大5件 |
| `evidence_preview` | string | Yes | 最上位根拠の先頭300文字以内 |
| `text_extraction_quality` | enum | No | `high`, `medium`, `low` |
| `downstream_priority` | enum | No | `high`, `medium`, `low`, `skip` |
| `needs_structured_extraction` | boolean | No | 後段抽出要否 |
| `candidate_stage` | enum | No | 本文判定状態 |
| `review_hint` | string | Yes | 人手レビュー理由 |
| `warning_codes` | JSON array string | No | 非致命的warning |
| `validation_errors` | JSON array string | No | 検証エラー |

---

## 4. enum

### 4.1 `document_type`

```text
earnings_release
earnings_presentation
forecast_revision
operating_update
business_plan
dividend_shareholder_return
financing_capital_policy
ma_restructuring
business_alliance
capex_fixed_assets
impairment
legal_regulatory
governance_personnel
sustainability
other
```

### 4.2 `topic_tags`

```text
performance
outlook
demand_sales
pricing
costs
foreign_exchange
inventory
supply_chain
investment_capacity
portfolio_change
partnership
capital_structure
shareholder_return
asset_impairment
legal_compliance
governance_organization
sustainability
other
```

topicは文書索引用の粗い分類であり、マクロテーマ確定値ではない。

### 4.3 `business_event_types`

```text
demand_change
price_change
cost_change
capacity_change
product_service_change
market_entry_exit
acquisition_disposal
partnership
restructuring
supply_disruption
workforce_change
other
```

### 4.4 `financial_impact_types`

```text
revenue
operating_profit
ordinary_profit
net_income
cash_flow
assets
liabilities
equity
capex
dividend
guidance
```

### 4.5 補助分類

`impact_direction`:

```text
positive
negative
mixed
neutral
unclear
```

`actual_or_forecast`:

```text
actual
forecast
both
unclear
not_applicable
```

`time_horizon`:

```text
immediate
current_period
next_period
medium_term
multiple
unclear
not_applicable
```

### 4.6 routing

`downstream_priority`:

```text
high
medium
low
skip
```

`candidate_stage`:

```text
body_supported
body_weak
body_unclassified
needs_review
```

---

## 5. 文書詳細JSON

詳細JSONがルールヒットと根拠の正本である。

```json
{
  "schema_version": "1.0.0",
  "enrichment_version": "2026-07-16.001",
  "enrichment_method": "rule_based",
  "document_id": "20260501_6753_a1b2c3d4",
  "source_metadata": {
    "source_id": "20260501123456",
    "disclosure_date": "2026-05-01",
    "disclosure_time": "15:00",
    "issuer_code": "6753",
    "issuer_name": "Example",
    "title": "業績予想の修正に関するお知らせ",
    "document_url": "https://example.invalid/document.pdf"
  },
  "classification": {
    "document_type": "forecast_revision",
    "document_type_candidates": [
      {"value": "forecast_revision", "score": 9}
    ],
    "topic_tags": ["outlook", "performance"],
    "business_event_types": ["demand_change"],
    "financial_impact_types": ["revenue", "operating_profit", "guidance"],
    "impact_direction": "negative",
    "actual_or_forecast": "forecast",
    "time_horizon": "current_period",
    "quantitative_data_present": true,
    "body_confidence": 0.88,
    "classification_reason": "タイトルと本文見出しが業績予想修正ルールに一致"
  },
  "evidence": [],
  "signals": {},
  "routing": {
    "downstream_priority": "high",
    "needs_structured_extraction": true,
    "candidate_stage": "body_supported",
    "review_hint": null
  },
  "quality": {
    "text_extraction_quality": "high",
    "warning_codes": []
  },
  "validation": {
    "status": "success",
    "errors": []
  },
  "generated_at_utc": "2026-07-16T10:00:00Z"
}
```

### 5.1 根拠オブジェクト

| フィールド | 型 | Nullable | 説明 |
|---|---|---:|---|
| `evidence_id` | string | No | 文書内一意 |
| `source_type` | enum | No | `block`, `table`, `mixed` |
| `source_ids` | string[] | No | block/table ID |
| `page_numbers` | integer[] | No | ページ番号 |
| `matched_rule_ids` | string[] | No | 一致ルール |
| `keyword_hits` | string[] | No | 一致語 |
| `text` | string | No | 原文、最大2,000文字 |
| `quality_score` | float | No | 0.0〜1.0 |

詳細JSONでは最大20件を保持する。CSVではconfidence順の最大5件の `evidence_ids` と、最上位根拠の先頭300文字以内を格納する単一の `evidence_preview` だけを保持する。

---

## 6. summary

テーブル名:

```text
tdnet_generic_body_enrichment_summary
```

主キー:

```text
run_id + source_id
```

| カラム | 型 | Nullable |
|---|---|---:|
| `run_id` | string | No |
| `target_date` | YYYYMMDD string | No |
| `source_id` | string | No |
| `document_id` | string | Yes |
| `status` | enum | No |
| `error_code` | string | Yes |
| `error_message` | string | Yes |
| `title` | string | Yes |
| `output_path` | path string | Yes |
| `document_type` | enum | Yes |
| `downstream_priority` | enum | Yes |
| `needs_structured_extraction` | boolean | No |
| `processing_duration_ms` | integer | Yes |
| `schema_version` | string | No |
| `enrichment_version` | string | No |

summary status:

```text
success
needs_review
failed
failed_validation
```

---

## 7. failed

テーブル名:

```text
tdnet_generic_body_enrichment_failed
```

主キー:

```text
run_id + source_id + error_code
```

| カラム | 型 | Nullable |
|---|---|---:|
| `run_id` | string | No |
| `target_date` | YYYYMMDD string | No |
| `source_id` | string | No |
| `document_id` | string | Yes |
| `title` | string | Yes |
| `error_code` | string | No |
| `error_message` | string | No |
| `retryable` | boolean | No |
| `schema_version` | string | No |
| `enrichment_version` | string | No |
| `generated_at_utc` | UTC datetime | No |

想定error code:

```text
missing_metadata_column
invalid_disclosure_date
preprocessed_document_not_found
ambiguous_preprocessed_document
missing_required_artifact
invalid_json
empty_document_blocks
preprocessing_failed
document_identity_mismatch
failed_validation
unexpected_error
```

---

## 8. report

日次・実行レポートに以下を持つ。

- `run_id`
- `schema_version`
- `enrichment_version`
- `started_at_utc`
- `finished_at_utc`
- `input_count`
- `matched_count`
- `processed_count`
- `success_count`
- `needs_review_count`
- `failed_validation_count`
- `failed_count`
- `document_type_counts`
- `priority_counts`
- `text_quality_counts`
- `error_code_counts`
- `needs_structured_extraction_count`
- `output_paths`

件数はsummary/failed/mainと収支一致しなければならない。

---

## 9. バリデーションルール

1. `document_id` は出力範囲内で一意
2. 全成果物でversionが空でない
3. enumとJSON配列要素はYAML定義内
4. `0.0 <= body_confidence <= 1.0`
5. `downstream_priority=high` ならconfidence 0.75以上かつ根拠あり
6. `needs_structured_extraction=true` なら:
   - priorityがhighまたはmedium
   - 根拠あり
   - text qualityがlowでない
   - 事業イベントまたは財務影響が1件以上
7. `candidate_stage=body_supported` ならconfidence 0.60以上かつ根拠あり
8. text qualityがlowなら`needs_review`かつstructured extraction=false
9. `failed_validation` とvalidation errorsの有無が一致
10. CSVのevidence IDが詳細JSONに存在
11. `evidence_preview` は根拠なしならnull、根拠ありなら詳細JSONの最上位根拠本文の先頭300文字と一致
12. 実行時失敗は主CSVへ出さない
13. reportの件数がsummary/failed/mainと一致

---

## 10. versioning

### `schema_version`

Semantic Versioningを使う。

- major: 削除、型変更、enum意味変更、必須化
- minor: nullable列・成果物・enum値の追加
- patch: 説明、例、互換性を壊さない制約明確化

### `enrichment_version`

`YYYY-MM-DD.NNN` とし、キーワード、重み、閾値、優先順位を変更したら更新する。

下流は構造互換性を `schema_version`、分類再現性を `enrichment_version` で判断する。

---

## 11. ETLノート

- CSVの配列はJSON文字列であり、DB取込時にARRAY/JSONへ変換する
- `disclosure_date`, `disclosure_time`, `generated_at_utc` は物理型へ変換する
- 証券コードは数値化せず文字列として保持する
- 空配列は `[]`、不明enumは `unclear` / `other` / `not_applicable` を意味に応じて使う
- `document_type_candidates`、詳細な根拠、候補score、ルールヒットは文書詳細JSONを参照する
- `evidence_preview` は一覧確認専用であり、監査・抽出には詳細JSONの完全な根拠を使う
- 顧客別・業種別フィールドを主テーブルへ追加せず、別の下流スキーマで管理する
