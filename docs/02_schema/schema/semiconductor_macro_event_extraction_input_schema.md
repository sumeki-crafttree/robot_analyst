# semiconductor_macro_event_extraction 入力スキーマ

## 関連リンク

- [入力スキーマYAML正本](semiconductor_macro_event_extraction_input_schema.yaml)
- [半導体マクロイベント抽出設計](../semiconductor_macro_event_extraction_design.md)
- [出力スキーマ解説](semiconductor_macro_event_extraction_output_schema.md)
- [出力スキーマYAML正本](semiconductor_macro_event_extraction_output_schema.yaml)
- [generic出力スキーマ解説](generic_body_metadata_enrichment_output_schema.md)
- [generic出力スキーマYAML](generic_body_metadata_enrichment_output_schema.yaml)
- [generic入力スキーマ解説](generic_body_metadata_enrichment_input_schema.md)
- [同業マクロ影響イベントDB設計](../peer_macro_event_db_design.md)
- [スキーマ索引](README.md)
- 020前処理実装: `020_prop_candidates/notebook/tdnet_pdf_preprocessing.py`

## 目次

1. [概要](#1-概要)
2. [業務上の意味](#2-業務上の意味)
3. [入力アーティファクト](#3-入力アーティファクト)
4. [論理URIとresolver](#4-論理uriとresolver)
5. [generic主CSV](#5-generic主csv)
6. [generic文書詳細JSON](#6-generic文書詳細json)
7. [020前処理成果物](#7-020前処理成果物)
8. [artifact graphと突合](#8-artifact-graphと突合)
9. [routing設定とselection decision](#9-routing設定とselection-decision)
10. [失敗・品質マトリクス](#10-失敗品質マトリクス)
11. [バリデーションとerror code](#11-バリデーションとerror-code)
12. [既知ギャップ](#12-既知ギャップ)
13. [version compatibility](#13-version-compatibility)
14. [運用](#14-運用)

---

## 1. 概要

- コンポーネント: `semiconductor_macro_event_extraction_input`
- スキーマ版: `1.0.0`
- 状態: `design_complete`
- 機械可読な正本: `semiconductor_macro_event_extraction_input_schema.yaml`
- 契約方式: `file_contract_only`
- 主結合キー: `document_id`

本スキーマは、generic本文メタデータ・エンリッチメントで抽出対象を索引し、そのgeneric根拠を020由来の本文ブロック・表へ遡って、半導体マクロイベント抽出へ渡す入力契約である。

021は020のPythonをimportせず、020リポジトリのコードや成果物を変更しない。remote/localを問わず論理URI resolverを介して各成果物を独立に解決する。同一相対配置、同一マウントポイント、共通リポジトリルートは前提にしない。

YAMLと本文が矛盾する場合はYAMLを正とする。

---

## 2. 業務上の意味

generic主CSVは、どの開示を後段へ回すかを高速に絞り込む索引である。文書詳細JSONはgeneric分類・routing・根拠の正本である。020成果物は、その根拠が実際にPDFのどのページ・本文ブロック・表から得られたかを再現する原典である。

役割を分ける理由は次のとおり。

1. CSVだけでは根拠本文が最大5 IDと300文字previewに縮退している。
2. 詳細JSONのgeneric evidenceには抽出元の `source_ids` がある。
3. `source_ids` を `block_id` / `table_id` に解決すると、LLMへ渡す範囲を必要箇所に限定できる。
4. `normalized.md` 全文をLLMへ渡さず、トークン浪費、ノイズ混入、監査不能を避けられる。
5. 020固有の不動産候補根拠と、021のgeneric根拠を混同しない。

`source_id` はTDnet開示の由来を示すが、`normalized.md` を含む020のper-document前処理成果物には出力されない。したがって前処理成果物への突合キーではない。

---

## 3. 入力アーティファクト

| アーティファクト | 必須 | 正本性 | 用途 |
|---|---:|---|---|
| generic日次または全体主CSV | Yes | 索引/projection | 対象候補の絞り込み |
| 該当 `document_id` の `generic_body_metadata_enrichment.json` | Yes | generic正本 | 分類、根拠、routing、品質、validation |
| `document_blocks.jsonl` | Yes | 本文根拠正本 | generic `source_ids` のblock解決 |
| `processing_report.json` | Yes | 前処理状態正本 | 成否、品質、ページ上限、件数 |
| `document_tables.jsonl` | Conditional | 表根拠正本 | table/mixed evidence参照時に必須 |
| `normalized.md` | No | 補助 | 監査、operator補助、resolver調査 |
| `candidate_evidence_spans.jsonl` | No / ignored | 使用禁止 | 不動産固有のlegacy候補根拠 |

主CSVは日次版または全体版の少なくとも一方を必要とする。両方に同じ `document_id` がある場合、契約対象フィールドは一致しなければならない。

`processing_report.json` は必須入力だが、020実装でPDFオープンや処理中に例外が発生すると、report生成箇所へ到達せずファイルが存在しないことがある。この場合は `processing_status=failed` を待つのではなく、`missing_processing_report` として `failed_precheck` にする。

---

## 4. 論理URIとresolver

### 4.1 URI形式

```text
artifact://{producer}/{artifact_name}/{document_id_or_scope}
```

例:

```text
artifact://generic/daily_main_csv/20260722
artifact://generic/document_detail/20260722_6753_a1b2c3d4
artifact://preprocessing/document_blocks/20260722_6753_a1b2c3d4
```

resolverは最低限、次を実装する。

```text
resolve(logical_uri) -> resolved_resource
exists(logical_uri) -> boolean
open_text(logical_uri, encoding) -> text_stream
```

`resolved_resource` は `logical_uri`, `access_uri`, `storage_kind` を持ち、`storage_kind` は `local` または `remote` である。

### 4.2 運用規則

- lineageには機械固有の絶対パスではなく論理URIを保存する。
- genericのパス文字列を置換して020パスを作らない。
- producer、artifact名、`document_id` / scopeで各成果物を個別解決する。
- remote objectを一時cacheしてもよいが、同じschema・hash・join検証を適用する。
- 0件は `resolver_no_match`、複数件は `resolver_ambiguous`。
- 読取権限や一時通信障害は他のschema不整合と分けて記録する。
- `processing_report.source_pdf_path` は020実行環境のlineageであり、resolver入力に使わない。

---

## 5. generic主CSV

### 5.1 必須列

全32列が必須である。Nullableは値のnull許容を表し、列自体の省略は許さない。

| 列 | 型 | Nullable | 説明 |
|---|---|---:|---|
| `schema_version` | string | No | generic出力契約版 |
| `enrichment_version` | string | No | genericルール実装版 |
| `enrichment_method` | string | No | `rule_based` |
| `document_id` | string | No | 主キー・全artifact joinキー |
| `source_id` | string | No | TDnet由来ID。前処理joinには不使用 |
| `disclosure_date` | date string | No | `YYYY-MM-DD` または `YYYYMMDD` |
| `disclosure_time` | time string | Yes | `HH:MM` / `HH:MM:SS` |
| `issuer_code` | string | No | 先頭0を保持 |
| `issuer_name` | string | No | 発行体名 |
| `title` | string | No | 開示タイトル |
| `document_url` | URI string | No | PDF原本URL |
| `status` | enum | No | `success`, `needs_review`, `failed_validation` |
| `document_type` | enum | No | generic文書種別 |
| `topic_tags` | JSON array string | No | generic topic |
| `business_event_types` | JSON array string | No | generic事業イベント |
| `financial_impact_types` | JSON array string | No | generic財務影響 |
| `impact_direction` | enum | No | `positive`, `negative`, `mixed`, `neutral`, `unclear` |
| `actual_or_forecast` | enum | No | `actual`, `forecast`, `both`, `unclear`, `not_applicable` |
| `time_horizon` | enum | No | `immediate`, `current_period`, `next_period`, `medium_term`, `multiple`, `unclear`, `not_applicable` |
| `quantitative_data_present` | boolean | No | 数値情報の有無 |
| `body_confidence` | float | No | 0.0〜1.0 |
| `evidence_ids` | JSON array string | No | 詳細JSONの根拠ID、最大5件 |
| `evidence_preview` | string | Yes | 最上位根拠の先頭300文字以内 |
| `classification_reason` | string | No | generic判定理由 |
| `text_extraction_quality` | enum | No | `high`, `medium`, `low` |
| `downstream_priority` | enum | No | `high`, `medium`, `low`, `skip` |
| `needs_structured_extraction` | boolean | No | 後段抽出要否 |
| `candidate_stage` | enum | No | `body_supported`, `body_weak`, `body_unclassified`, `needs_review` |
| `review_hint` | string | Yes | レビュー理由 |
| `warning_codes` | JSON array string | No | 非致命warning |
| `validation_errors` | JSON array string | No | generic検証エラー |
| `generated_at_utc` | UTC datetime | No | generic生成日時 |

`document_type`, `topic_tags`, `business_event_types`, `financial_impact_types` の全enumはYAMLの `enums` を正本とし、generic出力v1.0.0と一致する。未知値を `other` へ暗黙変換しない。

`disclosure_date` はgeneric producerが入力表記を保持するため、hyphen付き・なしの両方を受理する。consumerは日付partitionと比較に使う際に `YYYYMMDD` へ正規化し、producer原値はsource lineageに保持する。

### 5.2 JSON array stringのparse

対象は次の6列。

```text
topic_tags
business_event_types
financial_impact_types
evidence_ids
warning_codes
validation_errors
```

規則:

- JSON parserを厳密に1回適用し、結果がarrayであることを確認する。
- 各itemはstring。null、数値、object、nested arrayを拒否する。
- 空collectionは文字列 `[]` のみ。空文字、`null`、`None` は不可。
- Python reprの `['x']`、`x,y` のcomma split、scalar JSON `"x"` は不可。
- array順序を保持する。特に `evidence_ids` の順序は根拠優先順として扱う。

具体例:

```csv
topic_tags,business_event_types,evidence_ids,warning_codes
"[""supply_chain"",""investment_capacity""]","[""capacity_change""]","[""20260722_6753_a1b2c3d4_gev001""]","[]"
```

parse後:

```json
{
  "topic_tags": ["supply_chain", "investment_capacity"],
  "business_event_types": ["capacity_change"],
  "evidence_ids": ["20260722_6753_a1b2c3d4_gev001"],
  "warning_codes": []
}
```

不正例:

```text
['capacity_change']  # JSONではない
capacity_change      # arrayではない
""                   # 空配列ではない
null                 # non-nullable違反
```

### 5.3 booleanのparse

対象は `quantitative_data_present`, `needs_structured_extraction`。

現行Python generic CSV projectionがbooleanをcase-sensitiveな `True` / `False` の文字列として出力することを、既知producer契約のbaselineとする。

```csv
quantitative_data_present,needs_structured_extraction
True,False
```

前後空白を除いた後、case-sensitiveな `True` / `False` のみ許容する。`TRUE`, `false`, `1`, `0`, `yes`, 空文字は拒否する。文字列のtruthinessで `bool("False") == True` としてはならない。

### 5.4 CSVと詳細JSON

CSVは索引であり、詳細JSONからの決定的projectionである。選択前に少なくともversion、identity、classification、routing、quality、validation、CSV `evidence_ids` の整合を確認する。差異は `csv_detail_projection_mismatch` とする。根拠抽出に `evidence_preview` を使わない。

---

## 6. generic文書詳細JSON

### 6.1 top-level

| プロパティ | 型 | Nullable | 必須 |
|---|---|---:|---:|
| `schema_version` | string | No | Yes |
| `enrichment_version` | string | No | Yes |
| `enrichment_method` | string | No | Yes |
| `document_id` | string | No | Yes |
| `source_metadata` | object | No | Yes |
| `classification` | object | No | Yes |
| `evidence` | array | No | Yes |
| `signals` | object | No | Yes |
| `routing` | object | No | Yes |
| `quality` | object | No | Yes |
| `validation` | object | No | Yes |
| `generated_at_utc` | UTC datetime | No | Yes |

### 6.2 `source_metadata`

| フィールド | 型 | Nullable | 必須 |
|---|---|---:|---:|
| `source_id` | string | No | Yes |
| `disclosure_date` | date string | No | Yes |
| `disclosure_time` | time string | Yes | Yes |
| `issuer_code` | string | No | Yes |
| `issuer_name` | string | No | Yes |
| `title` | string | No | Yes |
| `document_url` | URI string | No | Yes |

`disclosure_time` はキー必須・値nullableである。

### 6.3 `classification`

| フィールド | 型 | Nullable | 必須 |
|---|---|---:|---:|
| `document_type` | enum | No | Yes |
| `document_type_candidates` | object[] | No | Yes |
| `topic_tags` | string[] | No | Yes |
| `business_event_types` | string[] | No | Yes |
| `financial_impact_types` | string[] | No | Yes |
| `impact_direction` | enum | No | Yes |
| `actual_or_forecast` | enum | No | Yes |
| `time_horizon` | enum | No | Yes |
| `quantitative_data_present` | boolean | No | Yes |
| `body_confidence` | float | No | Yes |
| `classification_reason` | string | No | Yes |

`document_type_candidates` の各要素は `value`（document_type enum、non-null）、`score`（integer、non-null）、`rule_id`（string、non-null）の3項目が必須である。配列型フィールドは空配列を許すがnullは許さない。

### 6.4 `evidence`

最大20件。各根拠は以下をすべて必須・non-nullで持つ。

| フィールド | 型 | 制約 |
|---|---|---|
| `evidence_id` | string | 文書内一意 |
| `source_type` | enum | `block`, `table`, `mixed` |
| `source_ids` | string[] | 1件以上 |
| `page_numbers` | integer[] | 1件以上、各値1以上 |
| `matched_rule_ids` | string[] | null不可 |
| `keyword_hits` | string[] | null不可 |
| `text` | string | 1〜2,000文字 |
| `quality_score` | float | 0.0〜1.0 |

`source_ids` はgeneric evidenceから020の `block_id` / `table_id` へ戻る唯一の根拠参照である。

例:

```json
{
  "evidence_id": "20260722_6753_a1b2c3d4_gev001",
  "source_type": "mixed",
  "source_ids": [
    "20260722_6753_a1b2c3d4_p003_b004",
    "20260722_6753_a1b2c3d4_p003_t001"
  ],
  "page_numbers": [3],
  "matched_rule_ids": ["business.capacity.expansion"],
  "keyword_hits": ["増産", "半導体"],
  "text": "半導体向け材料の生産能力を増強する。",
  "quality_score": 0.91
}
```

### 6.5 `signals`

| フィールド | 型 | Nullable | 内容 |
|---|---|---:|---|
| `matched_rule_ids` | string[] | No | 一致した全rule |
| `title_rule_ids` | string[] | No | titleで一致したrule |
| `negative_rule_ids` | string[] | No | negative hitしたrule |
| `rule_scores` | object<string, integer> | No | rule ID別score |
| `source_hit_counts` | object | No | `heading`, `body`, `table` の非負integer |
| `ambiguous_document_type` | boolean | No | 文書種別同点等の曖昧性 |

`signals` は診断・selection補助であり、根拠本文の代替ではない。

### 6.6 `routing`, `quality`, `validation`

`routing`:

| フィールド | 型 | Nullable |
|---|---|---:|
| `downstream_priority` | enum | No |
| `needs_structured_extraction` | boolean | No |
| `candidate_stage` | enum | No |
| `review_hint` | string | Yes |

`quality`:

| フィールド | 型 | Nullable |
|---|---|---:|
| `text_extraction_quality` | `high` / `medium` / `low` | No |
| `warning_codes` | string[] | No |

`validation`:

| フィールド | 型 | Nullable |
|---|---|---:|
| `status` | `success` / `needs_review` / `failed_validation` | No |
| `errors` | string[] | No |

`failed_validation` または非空 `errors` の文書は後段選択禁止である。

---

## 7. 020前処理成果物

定義は `020_prop_candidates/notebook/tdnet_pdf_preprocessing.py` の現行実装を正とする。既存generic input schemaに記載された将来候補や旧例ではなく、実際にemitされるshapeを契約化している。

### 7.1 `document_blocks.jsonl`

1行1本文ブロック。全フィールド必須・non-null。

| フィールド | 型 | 制約 |
|---|---|---|
| `block_id` | string | 主キー |
| `document_id` | string | 選択文書と一致 |
| `page_number` | integer | 1以上 |
| `page_layout_type` | enum | 下記4値 |
| `block_order` | integer | 1以上 |
| `block_type` | enum | 下記9値 |
| `text` | string | 空不可 |
| `normalized_text` | string | null不可 |
| `char_count` | integer | 0以上 |
| `bbox` | number[4] | 必ず4要素 |
| `extraction_method` | string | 現行は `pymupdf_text` |
| `quality_score` | float | 0.0〜1.0 |

実装上の `page_layout_type`:

```text
doc_like
slide_like
table_heavy
scanned_or_image
```

`mixed` は文書全体の `pdf_layout_type` では出得るが、現行の各block/tableには出ない。将来未知値は勝手に既存値へ寄せず `unsupported_enum_value` とし、producer fixture確認後にschemaを更新する。

実装上の `block_type`:

```text
document_title
page_title
section_heading
bullet
note
paragraph
header
footer
unknown
```

`slide_title`, `heading`, `table` は現行020実装のblock emit値ではない。将来対応はcompatibility reviewを要する。

### 7.2 `document_tables.jsonl`

表根拠を参照しない文書では任意。`source_type=table|mixed` または `source_ids` がtable IDを含む場合は必須。

| フィールド | 型 | Nullable | 制約 |
|---|---|---:|---|
| `table_id` | string | No | 主キー |
| `document_id` | string | No | 選択文書と一致 |
| `page_number` | integer | No | 1以上 |
| `page_layout_type` | enum | No | blocksと同じ4値 |
| `table_order` | integer | No | 1以上 |
| `markdown_table` | string | No | 空の場合もstring |
| `raw_cells_json` | string[][] | No | cell配列 |
| `extraction_method` | string | No | 現行は `pdfplumber_table` |
| `quality_score` | float | No | 0.0〜1.0 |

### 7.3 `processing_report.json`

現行020が正常にreport生成まで到達した場合、次をすべて必須・non-nullで出力する。

| フィールド | 型 | 制約・用途 |
|---|---|---|
| `document_id` | string | join |
| `source_pdf_path` | path string | lineageのみ |
| `sha256_hash` | hex string | 64文字 |
| `page_count` | integer | 1以上 |
| `pdf_layout_type` | enum | `doc_like`, `slide_like`, `table_heavy`, `scanned_or_image`, `mixed`, `unknown` |
| `page_layout_summary` | object | page layout別件数 |
| `text_char_count` | integer | 0以上 |
| `block_count` | integer | 0以上 |
| `table_count` | integer | 0以上 |
| `evidence_span_count` | integer | 監視のみ。generic根拠には不使用 |
| `document_text_extraction_quality` | enum | `high`, `medium`, `low` |
| `used_ocr` | boolean | 現行はfalse |
| `used_vision` | boolean | 現行はfalse |
| `ocr_candidate` | boolean | quality=lowの候補 |
| `processing_status` | enum | 実装値は `success`, `success_with_warnings` のみ |
| `errors` | string[] | table抽出warning等 |
| `processed_at_utc` | UTC datetime | report生成時刻 |

既存資料にある `processing_status=failed` は現行実装からはemitされない。失敗時はreportが不在になり得るため、consumerは不在を明示的に扱う。

### 7.4 `normalized.md`

監査・operator補助だけに使う。必要ならページ単位のbounded excerptを人手確認する。全文LLM投入は禁止する。generic evidenceの `source_ids` が解決可能な限り、本文根拠はblocks/tablesを使う。

### 7.5 ignored artifact

`candidate_evidence_spans.jsonl` とreportの `evidence_span_count` は020の不動産キーワード由来である。半導体マクロイベントのselection、prompt、confidence、根拠、出力へ一切使わない。

---

## 8. artifact graphと突合

```mermaid
flowchart LR
    C[generic daily/all main CSV<br/>index] -->|document_id| J[generic detail JSON<br/>canonical]
    J -->|evidence[].source_ids| B[document_blocks.jsonl]
    J -->|table source referenced| T[document_tables.jsonl]
    J -->|document_id / pages| R[processing_report.json]
    B --> P[bounded extraction context]
    T --> P
    R --> P
    N[normalized.md<br/>audit only] -. no full LLM input .-> O[operator]
    X[candidate_evidence_spans.jsonl] -. ignored .-> Z[no dependency]
```

突合順:

1. CSVの `document_id` で該当detailを1件解決する。
2. detail、report、全block、供給された全tableの `document_id` が完全一致することを確認する。
3. CSV `evidence_ids` がdetail `evidence[].evidence_id` に一意に存在することを確認する。
4. selectionではdetailの根拠集合を使用する。
5. 各generic evidenceの全 `source_ids` をblocks/tablesから1件ずつ解決する。
6. `source_type=block` はblockだけ、`table` はtableだけ、`mixed` は両方を最低1件ずつ要求する。
7. 解決元page集合と `evidence.page_numbers` 集合が一致することを確認する。
8. 全pageが `1..processing_report.page_count` に収まることを確認する。
9. `block_count` / `table_count` と実ファイル件数を照合する。

`source_id` はgeneric CSV/detail間では照合するが、020成果物のjoinには使わない。

---

## 9. routing設定とselection decision

### 9.1 設定object

`semiconductor_macro_event_routing`:

| 設定 | 型 | default | 意味 |
|---|---|---|---|
| `included_priorities` | enum[] | `["high","medium"]` | `low` は設定で追加可、`skip` は不可 |
| `requires_structured_extraction` | boolean | `true` | genericの抽出要否をguardにする |
| `allowed_generic_status` | enum[] | `["success","needs_review"]` | `failed_validation` は常に除外 |
| `priority_document_types` | enum[] | 下記8種 | 優先文書種別 |
| `low_quality_policy` | enum | `review_no_llm` | `skip` または `review_no_llm` |

優先文書種別:

```text
earnings_release
earnings_presentation
forecast_revision
business_plan
capex_fixed_assets
impairment
ma_restructuring
business_alliance
```

### 9.2 decision表

上から順に評価し、最初に一致したdecisionを採用する。

| 条件 | decision | LLM |
|---|---|---:|
| required artifact/schema/version/identity/evidence/page検証失敗 | `failed_precheck` | 禁止 |
| generic `failed_validation` | `skipped` | 禁止 |
| `needs_structured_extraction=false` | 原則 `skipped` | 禁止 |
| quality=`low`, policy=`review_no_llm` | `review_only` | 禁止 |
| quality=`low`, policy=`skip` | `skipped` | 禁止 |
| 根拠空、`source_ids` 空、未解決参照 | `failed_precheck` | 禁止 |
| priority/document_typeが設定対象外 | `skipped` | 禁止 |
| 全guard通過、根拠が完全解決 | `selected` | 許可 |

`needs_structured_extraction=false` のoperator overrideは、LLMを使わない `review_only` に限る。low qualityはいかなる設定でもLLMへ送らない。根拠空の文書をタイトルやpreviewだけで救済選択しない。

---

## 10. 失敗・品質マトリクス

| generic status | text quality | evidence | precheck | 標準decision | LLM |
|---|---|---|---|---|---:|
| `failed_validation` | any | any | any | `skipped` | No |
| `success` / `needs_review` | `low` | valid | pass | `review_only`（default） | No |
| `success` / `needs_review` | `low` | any | fail | `failed_precheck` | No |
| `success` / `needs_review` | `high` / `medium` | empty | pass相当 | `failed_precheck` | No |
| `success` / `needs_review` | `high` / `medium` | unresolved | fail | `failed_precheck` | No |
| `success` / `needs_review` | `high` / `medium` | valid | fail | `failed_precheck` | No |
| allowed | `high` / `medium` | valid | pass、routing対象 | `selected` | Yes |
| allowed | `high` / `medium` | valid | pass、routing対象外 | `skipped` | No |

precheckの方がgeneric statusによる通常skipより先に検出された場合は、データ契約異常を失わないよう `failed_precheck` を記録する。ただし `failed_validation` 行を抽出候補へ昇格させてはならない。

---

## 11. バリデーションとerror code

### 11.1 identity・projection

- CSV scope内の `document_id` は一意。
- 日次版と全体版の重複行は契約フィールド一致。
- detail/report/blocks/tablesの `document_id` は選択IDと一致。
- CSVとdetailのsource metadata、classification、routing、quality、validationが一致。
- CSV `evidence_ids` はdetailへ一意に解決。

主なcode:

```text
duplicate_document_id
document_id_mismatch
csv_detail_projection_mismatch
unresolved_generic_evidence_id
```

### 11.2 schema・parse

```text
invalid_csv_header
invalid_csv_json_array
invalid_csv_boolean
invalid_json
invalid_jsonl
unsupported_schema_version
unsupported_enum_value
```

enum未知値、nullable違反、必須キー欠損を黙って補完しない。

### 11.3 artifact・resolver

```text
missing_generic_main_csv
missing_generic_detail
missing_document_blocks
missing_processing_report
missing_referenced_document_tables
resolver_no_match
resolver_ambiguous
resolver_access_denied
resolver_transient_error
```

`resolver_access_denied` と `resolver_transient_error` はretry可能。0件、複数件、契約不整合は設定やデータを直すまで非retry扱いである。

### 11.4 evidence・page

```text
empty_generic_evidence
duplicate_generic_evidence_id
empty_evidence_source_ids
unresolved_evidence_source_id
evidence_source_type_mismatch
evidence_page_mismatch
page_out_of_range
preprocessing_count_mismatch
```

generic evidence本文と `source_ids` 由来本文に差があっても、自動的に文字列一致へ丸めない。source参照とpageが整合することを最低条件とし、必要なら差異を監査ログへ記録する。

### 11.5 policy

```text
generic_failed_validation
preprocessing_status_invalid
low_text_quality_no_llm
normalized_markdown_fulltext_forbidden
legacy_evidence_ignored
```

policy違反でLLM呼出し前に停止する。LLM呼出し後に結果を捨てる運用では、情報漏えい・コスト抑制guardにならない。

---

## 12. 既知ギャップ

### 12.1 020とのギャップ

1. 020は `normalized.md` を含む全per-document前処理成果物に `source_id` を出力しない。前処理成果物とは `document_id` だけでjoinする。
2. `candidate_evidence_spans.jsonl` は不動産語彙で生成され、半導体用途には使えない。
3. 020はOCR/visionを実行せず、`used_ocr=false`, `used_vision=false`。low quality文書をLLMで補う運用は禁止する。
4. 020のpage-level layout実値は4種。既存generic入力資料にあるblock/tableの `mixed` は現行emit値ではない。
5. 020のblock type実値は9種。既存generic入力資料の `slide_title`, `heading`, `table` は現行emit値ではない。
6. 020のreport status実値は `success`, `success_with_warnings` のみ。処理失敗ではreport自体が不在になり得る。
7. reportの `evidence_span_count` はlegacy不動産evidence件数で、generic evidence件数ではない。
8. `normalized.md` は本文と表を再構成するが、厳密なsource ID参照を持たないためcanonical joinには使わない。

### 12.2 genericとのギャップ

1. generic CSVは最大5 evidence ID、preview最大300文字であり、完全な根拠ではない。
2. generic detailは最大20 evidenceを持つ。抽出時はdetailを正本にする。
3. generic `status=needs_review` は自動除外ではないが、品質・routing・根拠guardを別途通す。
4. generic `needs_structured_extraction=false` は標準でskip。半導体抽出側が独自にtrueへ書き換えない。
5. generic topic/event分類は汎用であり、半導体macro themeの確定値ではない。後段抽出の候補・contextとして使う。
6. generic `signals` はrule診断であり、原文根拠ではない。
7. generic schemaが同じでも `enrichment_version` 変更でselection分布が変わり得る。

---

## 13. version compatibility

### 13.1 本契約

Semantic Versioningを使う。

- major: 削除、型/意味変更、必須artifact・必須field追加、nullableからnon-nullable、非互換enum変更
- minor: 後方互換な任意field/artifact、明示的に許容するenum追加
- patch: accepted dataを変えない説明・例・制約明確化

### 13.2 generic

baselineはgeneric schema `1.0.0`。同一majorでも自動許可せず、required、型、nullable、enum、projection意味を検査する。`enrichment_version` はexact valueをlineageへ保存し、変更時は選択件数、priority比率、根拠解決率、low quality率を再評価する。

### 13.3 020

baselineは `020_prop_candidates/notebook/tdnet_pdf_preprocessing.py` の現行shape。020に独立schema version fieldがないため、実装変更時は固定fixtureでfields、enum、nullability、件数、page整合を検査する。未知値は互換性ありと推測しない。

### 13.4 resolver

logical URIのidentityと取得bytesが保たれる限り、localからremote、bucket変更、mount変更は本データschemaのversion変更を要しない。resolverが複数候補を返す変更は非互換である。

---

## 14. 運用

### 14.1 推奨処理順

1. routing設定とproducer対応versionを固定する。
2. 日次/全体CSVをresolveし、headerとparse規則を検証する。
3. CSVでpriority、status、document typeを粗く絞る。
4. 各 `document_id` のdetail/report/blocksをresolveする。
5. detailを正本としてCSV projectionを照合する。
6. generic evidenceの `source_ids` を解決し、必要時だけtablesをresolveする。
7. identity、page、count、quality、policyを検証する。
8. decisionを1件記録する。
9. `selected` だけをbounded blocks/tables contextでLLMへ渡す。
10. logical URI、versions、decision、error/warning、使用したevidence/source IDsをlineageへ残す。

### 14.2 LLM入力

- generic evidenceごとに解決したblock/tableだけを構成する。
- page、`block_id` / `table_id`、generic `evidence_id` をprompt metadataに含める。
- 文書全体を必要とする設計へ暗黙拡張しない。
- header/footerは必要性を評価し、単独根拠にしない。
- table evidence参照時にtable fileがなければ本文だけで代替せず失敗させる。
- low qualityはpromptを作成しない。

### 14.3 監視指標

- decision別件数: `selected`, `skipped`, `review_only`, `failed_precheck`
- error code別件数
- generic status / priority / document type別選択率
- text quality別件数
- evidence/source ID解決率
- table参照率とtable欠損率
- resolver storage kind別成功率・latency
- producer schema/enrichment version別件数

### 14.4 監査

抽出結果から次を逆引きできるようにする。

```text
extraction record
  -> document_id
  -> generic evidence_id
  -> source block_id/table_id
  -> page_number
  -> logical_uri
  -> producer versions
```

remote cacheのローカル一時パスは監査identityにしない。原典のlogical URIと、取得時に利用可能ならcontent hashを保存する。
