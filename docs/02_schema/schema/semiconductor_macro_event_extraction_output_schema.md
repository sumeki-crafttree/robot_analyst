# semiconductor macro event extraction 出力スキーマ

## 関連リンク

- [半導体マクロイベント抽出設計](../semiconductor_macro_event_extraction_design.md)
- [入力スキーマ解説](semiconductor_macro_event_extraction_input_schema.md)
- [入力スキーマYAML正本](semiconductor_macro_event_extraction_input_schema.yaml)
- [汎用本文メタデータ・エンリッチメント設計](../generic_body_metadata_enrichment_design.md)
- [汎用本文メタデータ出力スキーマ解説](generic_body_metadata_enrichment_output_schema.md)
- [汎用本文メタデータ出力スキーマYAML正本](generic_body_metadata_enrichment_output_schema.yaml)
- [本出力スキーマYAML正本](semiconductor_macro_event_extraction_output_schema.yaml)
- [スキーマ索引](README.md)

## 目次

1. [概要](#1-概要)
2. [業務上の意味と粒度](#2-業務上の意味と粒度)
3. [出力成果物](#3-出力成果物)
4. [canonical文書JSON](#4-canonical文書json)
5. [イベントモデル](#5-イベントモデル)
6. [taxonomy](#6-taxonomy)
7. [nullableとother](#7-nullableとother)
8. [CSV・JSONL projection](#8-csvjsonl-projection)
9. [summary・failed・review・report](#9-summaryfailedreviewreport)
10. [例](#10-例)
11. [バリデーション](#11-バリデーション)
12. [versionと運用](#12-versionと運用)

---

## 1. 概要

- コンポーネント: `semiconductor_macro_event_extraction`
- スキーマ版: `1.0.0`
- 状態: `design_complete`
- 機械可読な正本: `semiconductor_macro_event_extraction_output_schema.yaml`
- 出力ルート: `data/processed/tdnet_semiconductor_macro_events_extracted/`
- canonical粒度: 1ファイル = 1処理済み開示文書
- 分析粒度: 1 event object / CSV・JSONL row = 原則「1社 × 1開示 × 1 macro theme L1/L2 × 1 business impact」
- 文書あたりイベント数: `0..N`

YAMLを型、enum、列順、制約の正本とし、本書は業務上の意味、例、projection、運用を説明する。canonical文書JSONからイベントCSV・JSONLを決定的に生成し、形式ごとに抽出処理を再実行しない。

---

## 2. 業務上の意味と粒度

本出力は、半導体企業のTDnet開示から「どのマクロ環境が、企業のどの対象へ、どの仕組みで影響したか」を根拠付きイベントとして記録する。単なる単語出現ではなく、次の4要素が揃ったものだけをイベントとする。

1. マクロ事象の方向
2. 影響対象。全社の場合は `company_wide` でよい
3. business impactを説明する `impact_mechanism`
4. 投入されたgeneric evidence集合へ解決できる根拠

同じL1/L2でも、異なるセグメント、製品、地域、顧客群、または異なるimpact mechanismなら別イベントになり得る。反対に、同じbusiness impactに複数の財務指標が記載されていてもイベントを分割せず、1イベントの `financial_impacts[]` に保持する。

`event_id` は文書内イベントの永続ID、`dedup_key` は文書横断の重複候補を束ねる別キーである。両者を代用してはならない。

---

## 3. 出力成果物

### 3.1 日次

| アーティファクト | パス | 粒度 |
|---|---|---|
| canonical文書JSON | `{yyyymmdd}/documents/{document_id}/semiconductor_macro_event_extraction.json` | 1ファイル=1処理済み文書 |
| event JSONL | `{yyyymmdd}/semiconductor_macro_events.jsonl` | 1行=1イベント |
| event CSV | `{yyyymmdd}/semiconductor_macro_events.csv` | 1行=1イベント |
| summary CSV | `{yyyymmdd}/semiconductor_macro_event_extraction_summary.csv` | 1行=1入力文書 |
| failed CSV | `{yyyymmdd}/semiconductor_macro_event_extraction_failed.csv` | 1行=1失敗 |
| review queue CSV | `{yyyymmdd}/semiconductor_macro_event_review_queue.csv` | 1行=1レビュー項目 |
| daily report JSON | `{yyyymmdd}/daily_semiconductor_macro_event_extraction_report.json` | 1ファイル=1日 |

### 3.2 run-level aggregate

| アーティファクト | パス |
|---|---|
| event JSONL | `semiconductor_macro_events_all.jsonl` |
| event CSV | `semiconductor_macro_events_all.csv` |
| summary CSV | `semiconductor_macro_event_extraction_summary_all.csv` |
| failed CSV | `semiconductor_macro_event_extraction_failed_all.csv` |
| review queue CSV | `semiconductor_macro_event_review_queue_all.csv` |
| report JSON | `semiconductor_macro_event_extraction_report_all.json` |

CSVは `utf-8-sig`、JSON/JSONLはUTF-8で非ASCII文字を保持する。run-level aggregateは対象日次成果物の決定的な和集合であり、主キー重複はエラーとする。

実行時失敗はcanonical JSONとevent JSONL/CSVを作らない。summaryに `failed`、failed CSVに原因を記録する。スキーマ検証まで到達した `failed_validation` は監査可能性のためcanonical JSONを保持するが、無効なイベントを主event行へ投影しない。

routing段階の `skipped`, `review_only`, `failed_precheck` もcanonical JSONを作らない場合がある。ただし、入力総数との収支を保つため、routingされた全inputにsummaryを必ず1行出す。

---

## 4. canonical文書JSON

トップレベルは次の順序・意味を持つ。

| フィールド | 型 | Nullable | 意味 |
|---|---|---:|---|
| `schema_version` | string | No | 出力契約版。`1.0.0` |
| `extraction_version` | string | No | 抽出ロジック・prompt・閾値版 |
| `taxonomy_version` | SemVer string | No | taxonomy版。現行 `1.0.0` |
| `document_id` | string | No | preprocessingから引き継ぐ文書ID |
| `source_metadata` | object | No | 開示原本メタデータ |
| `input_versions` | object | No | preprocessingとgeneric enrichmentの入力版 |
| `extraction_provenance` | object | No | モデル実行・コンテキスト・費用情報 |
| `extraction_status` | enum | No | 文書単位結果 |
| `events` | array | No | `0..N`イベント。空は `[]` |
| `warnings` | array | No | 非致命的warning。空は `[]` |
| `validation` | object | No | 検証結果とエラー |
| `generated_at_utc` | UTC datetime | No | 生成日時 |

### 4.1 extraction status

| 値 | 意味 | canonical | main event rows |
|---|---|---:|---:|
| `success` | 1件以上の妥当なイベント、レビュー不要 | あり | あり |
| `no_event_found` | 根拠を満たすイベントなし | あり、`events=[]` | なし |
| `needs_review` | 1件以上がレビュー条件に該当 | あり | 妥当なイベントのみあり |
| `failed_validation` | canonical候補が検証不合格 | あり | なし |
| runtime `failed` | 入力、provider、timeout等で抽出未完了 | なし | なし |

`failed` はcanonicalの `extraction_status` ではなくsummary statusである。

### 4.2 source metadata

required keyは次のとおり。nullable keyも省略せず、値がなければJSON nullで出す。

| フィールド | 型 | Nullable | 説明 |
|---|---|---:|---|
| `source_id` | string | No | 開示元ID |
| `disclosure_date` | date string | No | 開示日 |
| `disclosure_time` | time string | Yes | 開示時刻 |
| `issuer_code` | string | No | 発行体コード |
| `issuer_name` | string | No | 発行体名 |
| `title` | string | No | 開示タイトル |
| `document_url` | URI string | No | 原本URL |
| `document_type` | enum | No | generic enrichment v1.0.0のdocument type |
| `issuer_value_chains` | value_chain enum array | Yes | 発行体レベル分類 |
| `issuer_value_chain_raw` | string array | Yes | 発行体分類の原文・設定ラベル |

`document_type` は `earnings_release`, `earnings_presentation`, `forecast_revision`, `operating_update`, `business_plan`, `dividend_shareholder_return`, `financing_capital_policy`, `ma_restructuring`, `business_alliance`, `capex_fixed_assets`, `impairment`, `legal_regulatory`, `governance_personnel`, `sustainability`, `other` のいずれかとする。

`issuer_value_chains` は保守された発行体設定、または明示的な原文根拠からのみ設定する。根拠がない発行体分類をLLMで推測・補完してはならず、その場合は `issuer_value_chains=null`, `issuer_value_chain_raw=null` とする。

### 4.3 input versions

| フィールド | 型 | 説明 |
|---|---|---|
| `preprocessing_contract_reference` | string | `020_prop_candidates/notebook/tdnet_pdf_preprocessing.py`。可能ならsource revisionまたはcontent hashをsuffixとして併記 |
| `preprocessing_artifact_hashes` | object | 消費したpreprocessing artifact名/pathからcontent hashへのmap |
| `generic_enrichment_schema_version` | string | generic出力契約版 |
| `generic_enrichment_version` | string | generic enrichment実装版 |

020 preprocessingには独立した `preprocessing_schema_version` がないため、このキーは使用しない。

### 4.4 extraction provenance

| フィールド | Nullable | 説明 |
|---|---:|---|
| `llm_called` | No | LLM呼出し有無 |
| `provider` | Yes | 推論provider |
| `model` | Yes | モデル名 |
| `model_version` | Yes | providerが返す固定版。取得不能ならnull |
| `prompt_version` | No | prompt契約版 |
| `context_set_version` | No | コンテキスト選択・構成版 |
| `temperature` | Yes | 実行temperature |
| `attempt_count` | No | LLM試行数。0以上 |
| `fallback_used` | No | fallback利用有無 |
| `token_usage` | Yes | input/output/total token。provider非対応ならnull |
| `input_evidence_ids` | No | モデルへ投入したgeneric evidence ID。空なら `[]` |
| `context_hashes` | No | 投入コンテキストの内容hash。空なら `[]` |
| `latency_ms` | Yes | end-to-end推論時間 |
| `cost` | Yes | `{amount, currency}`。算出不能ならnull |

`llm_called=false` なら `provider`, `model`, `model_version`, `temperature`, `token_usage`, `cost` はnull、`attempt_count=0` とする。`llm_called=true` なら `provider`, `model`, `temperature` はnon-null、`attempt_count>=1` とし、non-nullの `prompt_version`, `context_set_version` と併せて記録する。rule-only処理でもprompt/context契約の代替ルール版として両versionを保持できる。

モデル名だけで再現性を判断せず、`model_version`, `prompt_version`, `context_set_version`, input evidence、context hashを併用する。

---

## 5. イベントモデル

### 5.1 必須フィールド

| フィールド | 意味 |
|---|---|
| `event_id` | 文書IDとcanonical fingerprintから生成する決定的ID |
| `dedup_key` | 文書横断重複候補用の決定的キー |
| `macro_theme_l1`, `macro_theme_l2` | 親子関係を持つマクロtaxonomy |
| `event_direction` | マクロ事象そのものの方向 |
| `impact_direction` | 企業・事業への総合的business effect |
| `impact_strength` | 開示中で表現された影響強度 |
| `time_horizon` | 影響時期 |
| `actual_or_forecast` | 実績・予想区分 |
| `impact_scope` | 影響対象の粒度 |
| `impact_mechanism` | 企業・事業へ効く仕組み |
| `normalized_summary` | 根拠範囲内の簡潔な正規化要約 |
| `financial_impacts` | 財務影響配列。記載がなければ `[]` |
| `evidence_refs` | 1〜8件の根拠参照 |
| `confidence` | 0.0〜1.0 |
| `needs_human_review` | 人手確認要否 |
| `review_reasons` | レビュー理由。不要なら `[]` |

### 5.2 対象フィールド

`company_segment_raw`, `company_product_raw`, `normalized_segment`, `normalized_product_group`, `device_category`, `device_category_raw`, `technology_node`, `end_market`, `end_market_raw`, `customer_group`, `region` はnullableである。`semiconductor_value_chain`, `semiconductor_value_chain_raw`, `region_raw` もnullableで保持する。

`source_metadata.issuer_value_chains` は発行体全体の分類、`semiconductor_value_chain` は当該イベントが対象とするvalue chainであり、意味と根拠を分離する。issuer分類をeventへコピーするだけの補完や、event記載からissuer分類を逆算することはしない。

`semiconductor_value_chain_raw`, `device_category_raw`, `end_market_raw` はevent対象の原文表現を保持するnullable stringである。対応する正規化値が `other` の場合はrawをnon-null必須とする。`device_category=null` / `end_market=null` なら対応rawも原則nullとし、記載なしの値をrawだけで補わない。fingerprintには正規化済みtaxonomy値だけを含め、これらのrawは含めない。

ただし、フィールドがnullableであることと対象根拠が不要であることは同義ではない。`impact_scope != company_wide` なら、選択したscopeに対応する対象フィールドと根拠が必要である。全社影響が明記される場合は `impact_scope=company_wide` とし、個別対象フィールドをすべてnullにできる。

### 5.3 financial impacts

財務影響はイベント内の `financial_impacts[]` として保持する。財務記載がなければ `[]`、1指標なら1 object、同じbusiness impactに複数指標があれば複数objectとする。

各objectは次を持つ。event top-levelの `impact_direction` はbusiness impact全体の方向、各 `financial_impacts[].impact_direction` は個別財務指標の方向であり、別フィールドである。

- `financial_metric`
- `impact_direction`
- `amount_value`
- `amount_unit`
- `period`
- `actual_or_forecast`
- `offsetting_factor`

金額のない定性的影響を許容し、その場合は `amount_value=null` かつ `amount_unit=null` とする。一方だけをnullにはできない。`period` と `offsetting_factor` は原文にない場合nullでよい。

### 5.4 evidence ref

各イベントは `evidence_refs` を1〜8件持つ。9件以上の候補がある場合は、必須フィールドの支持範囲、exact quote一致、source品質、独立性の順で決定的に8件へ絞り、切り捨てた根拠IDをwarningへ記録する。各 `evidence_ref` の必須フィールド:

| フィールド | 要件 |
|---|---|
| `evidence_id` | 同じ文書の投入generic evidence集合内に一意に解決 |
| `source_type` | `block`, `table`, `mixed` |
| `source_ids` | 1件以上。generic evidenceと一致 |
| `page_numbers` | 1件以上。generic evidenceと一致 |
| `quote` | 1〜2,000文字。正規化後に根拠本文の完全なsubstring |

quote照合時はNFKC、改行統一、連続Unicode空白の1空白化を行う。要約や言い換えをquoteとして保存しない。企業、製品、地域、数値、期間、方向、因果関係はすべて `evidence_refs` で裏付ける。

### 5.5 deterministic identity

`event_id`:

```text
evt_ + first_24_hex(
  SHA-256(document_id + U+001F + canonical_fingerprint)
)
```

canonical fingerprintはtheme、event/business方向、時間軸、実績予想区分、scope、mechanism、対象、canonical化した `financial_impacts` から構成する。`impact_strength` は抽出品質・review判断で再評価され得る属性として意図的に除外し、このラベルだけの再評価では `event_id` を変えない。`normalized_summary` と `evidence_refs` も含めないため、LLMの言い換えや根拠列挙順だけではIDが変わらない。文字列はNFKC、trim、空白圧縮し、taxonomy値はlowercase、nullはJSON literal `null`、object keyはスキーマ順、JSONは余分な空白なしとする。`financial_impacts` は各objectのcanonical JSON順に整列する。

`dedup_key` は issuer、theme、方向、scope、mechanism、対象、時間軸等のYAML指定fingerprintから生成する。

```text
dedup_ + first_24_hex(SHA-256(canonical_dedup_fingerprint))
```

抽出順、モデルが返した配列順、日次ファイル内の行順はIDへ影響しない。hash衝突時に連番suffixを付けず、validation errorとする。

---

## 6. taxonomy

### 6.1 macro theme親子表

`macro_theme_l2` は必ず同じ行のL1に属する値を使う。

| L1 | 許可するL2 |
|---|---|
| `end_market_demand` | `ai_server_demand`, `hyperscaler_demand`, `pc_smartphone_demand`, `automotive_ev_demand`, `industrial_demand`, `consumer_electronics_demand`, `telecom_demand`, `other_end_market_demand` |
| `ai_datacenter_capex` | `ai_server_investment`, `hyperscaler_capex`, `datacenter_capex`, `ai_accelerator_investment`, `datacenter_power_infrastructure`, `other_ai_datacenter_capex` |
| `semiconductor_cycle` | `cycle_upturn`, `cycle_downturn`, `demand_recovery`, `demand_slowdown`, `supply_demand_balance`, `other_semiconductor_cycle` |
| `memory_pricing` | `dram_pricing`, `nand_pricing`, `hbm_pricing`, `memory_contract_pricing`, `memory_spot_pricing`, `other_memory_pricing` |
| `inventory` | `inventory_build`, `inventory_adjustment`, `inventory_normalization`, `channel_inventory`, `customer_inventory`, `other_inventory` |
| `customer_capex` | `foundry_capex`, `memory_capex`, `wfe_capex`, `logic_capex`, `other_customer_capex` |
| `capacity_supply` | `utilization`, `new_fab`, `capacity_expansion`, `capacity_reduction`, `supply_shortage`, `oversupply`, `other_capacity_supply` |
| `technology_transition` | `node_transition`, `gaa`, `advanced_packaging`, `euv`, `sic_gan`, `hbm_transition`, `other_technology_transition` |
| `fx` | `yen_appreciation`, `yen_depreciation`, `currency_translation`, `transaction_fx`, `other_fx` |
| `input_cost` | `energy_cost`, `material_cost`, `silicon_wafer_cost`, `chemical_gas_cost`, `labor_cost`, `other_input_cost` |
| `geopolitics_export_control` | `export_control`, `china_us_geopolitics`, `tariff_trade_restriction`, `economic_security`, `regional_conflict`, `other_geopolitics` |
| `industrial_policy_subsidy` | `semiconductor_subsidy`, `tax_incentive`, `domestic_fab_policy`, `localization_policy`, `other_industrial_policy` |
| `logistics_supply_chain` | `logistics_disruption`, `lead_time_change`, `supplier_disruption`, `procurement_constraint`, `supply_chain_normalization`, `other_logistics_supply_chain` |
| `financial_conditions` | `interest_rate`, `funding_cost`, `credit_availability`, `liquidity_conditions`, `other_financial_conditions` |

### 6.2 その他の固定enum

- `value_chain`: `idm`, `fabless`, `foundry`, `memory`, `logic`, `analog`, `power_semiconductor`, `semiconductor_equipment`, `inspection_metrology`, `semiconductor_materials`, `silicon_wafer`, `electronic_components`, `osat_packaging_test`, `semiconductor_distributor`, `facility_infrastructure`, `other`
- `device_category`: `dram`, `nand`, `hbm`, `logic`, `mcu`, `analog`, `power`, `sensor`, `foundry_service`, `equipment`, `materials`, `wafer`, `packaging`, `other`
- `end_market`: `ai_server`, `datacenter`, `smartphone`, `pc`, `automotive`, `industrial`, `consumer_electronics`, `telecom`, `medical`, `defense_aerospace`, `other`
- `event_direction`: `increase`, `decrease`, `improving`, `deteriorating`, `tightening`, `easing`, `stable`, `mixed`, `unclear`
- `impact_direction`: `positive`, `negative`, `mixed`, `neutral`, `unclear`
- `region`: `japan`, `north_america`, `europe`, `china`, `taiwan`, `south_korea`, `asia_ex_china`, `global`, `other`
- `impact_strength`: `high`, `medium`, `low`, `unclear`
- `time_horizon`: `immediate`, `current_period`, `next_period`, `medium_term`, `multiple`, `unclear`
- `actual_or_forecast`: `actual`, `forecast`, `both`, `unclear`, `not_applicable`
- `impact_scope`: `company_wide`, `segment`, `product`, `device`, `end_market`, `customer_group`, `region`, `multiple`

`impact_mechanism`:

```text
volume_up, volume_down, asp_up, asp_down, cost_up, cost_down,
margin_up, margin_down, utilization_up, utilization_down,
inventory_increase, inventory_reduction, capacity_expansion,
capacity_reduction, order_increase, order_decrease,
backlog_increase, backlog_decrease, supply_constraint,
technology_mix_improvement, technology_obsolescence,
capex_increase, capex_decrease
```

`financial_metric`:

```text
revenue, operating_profit, gross_margin, net_income, capex,
inventory, inventory_days, orders, backlog, shipments, asp,
utilization_rate, production_capacity, wafer_starts,
book_to_bill, free_cash_flow
```

---

## 7. nullableとother

原則は全taxonomyで共通である。

- `null`: 原文に記載がない、または当該イベントに非該当
- `other`: 原文には対象が明示されているが、管理taxonomy外
- `unclear`: 対象値は記載されている可能性があるが、方向・区分を確定できない
- 空文字: nullの代用に使わない

例えば製品の記載自体がなければ `device_category=null`, `device_category_raw=null`、明示された製品がdevice taxonomy外なら `device_category=other` とし `device_category_raw` に原文を残す。end marketも同様に、`end_market=other` なら `end_market_raw` はnon-null、`end_market=null` なら `end_market_raw` も原則nullとする。`region=other` の場合は `region_raw`、製品・セグメントは `company_product_raw` / `company_segment_raw` に原文を残す。

L2の `other_*` も同じ意味であり、テーマ自体が不明という意味ではない。親L1は根拠から確定できるが、明示された具体テーマがL2 taxonomy外の場合に限る。

---

## 8. CSV・JSONL projection

### 8.1 基本原則

canonical文書JSONが正本であり、event JSONLとCSVで別抽出を行わない。両形式は同じcanonical eventから、用途別に次の規則で投影する。

#### 8.1.1 JSONL envelope

JSONLの各行はYAML `objects.event_jsonl_envelope` に従うlossless envelopeである。`schema_version`, `extraction_version`, `taxonomy_version`, `document_id`, `source_metadata`, `extraction_status`, `extraction_provenance`, `event`, `generated_at_utc` をrequired propertiesとして持つ。nested objectと配列は文字列化せずnative JSONのまま保持する。1行1eventとし、eventなし文書は0行、行順は `document_id`, `event_id` 昇順とする。

#### 8.1.2 CSV flat projection

1. 文書トップのversion、source metadata、provenanceをイベントへ付加する。
2. event objectをYAML `tables.event_projection.column_order` へフラット化する。
3. 配列・objectは完全な `*_json` 列へcompact JSONで格納する。
4. `document_id`, `event_id` 昇順で並べる。

### 8.2 lossless financial projection

`financial_impacts_json` は常にcanonical `financial_impacts` の完全なcompact JSONである。

| financial_impacts件数 | `financial_impacts_json` | convenience列 |
|---:|---|---|
| 0 | `[]` | すべてnull |
| 1 | 1 objectを含むJSON array | 7列すべてを同じobjectから設定 |
| 2以上 | 全objectを含むJSON array | 7列すべてnull |

7つのconvenience列は `financial_metric`, `financial_impact_direction`, `amount_value`, `amount_unit`, `financial_period`, `financial_actual_or_forecast`, `offsetting_factor` である。YAMLのcolumn orderにはこれらに加えてprojection全列を定義している。複数objectの「先頭」だけを入れてはならない。

### 8.3 JSON列とnull

- `financial_impacts_json`, `evidence_refs_json`, `evidence_ids_json`, `review_reasons_json` はRFC 8259 compact JSON
- 空配列は `[]`
- CSV nullは引用符なしの空field
- literal空文字は `""`
- booleanは `true` / `false`
- 日時はUTC RFC 3339、末尾 `Z`
- 金額は桁区切りなしの10進数
- object keyはスキーマ順、不要な空白なし

これにより `*_json` 列からcanonicalの配列・objectを決定的に復元できる。

### 8.4 event CSV列順

完全な列順はYAML `tables.event_projection.column_order` を正本とする。大区分は次の順である。

1. version
2. document/source metadata
3. event identityとtaxonomy
4. `event_direction`, event top-level `impact_direction`, `semiconductor_value_chain`, `semiconductor_value_chain_raw` を含む対象とbusiness impact
5. `financial_impacts_json` と単一object convenience列
6. evidence JSON
7. confidence/review
8. status/provenance/generated timestamp

source metadata投影では `document_url` の直後にrequired `document_type` を置く。対象taxonomy投影では `device_category` の直後に `device_category_raw`、`end_market` の直後に `end_market_raw` を置く。

---

## 9. summary・failed・review・report

### 9.1 summary

`tdnet_semiconductor_macro_event_extraction_summary` はrouting段階でcanonicalを作らなかった入力も含め、全入力文書ごとに必ず1行を持つ。主キーは `run_id + source_id`。statusは `success`, `no_event_found`, `needs_review`, `failed_validation`, `failed`, `skipped`, `review_only`, `failed_precheck` である。

主な列は、文書ID、status、event件数、review event件数、error、canonical path、処理時間、3種version、生成日時である。`failed`, `skipped`, `review_only`, `failed_precheck` では `canonical_json_path=null` を許容する。

### 9.2 failed

`tdnet_semiconductor_macro_event_extraction_failed` は1失敗1行。主キーは `run_id + source_id + error_code`。`stage`, `error_code`, `error_message`, `retryable`, `canonical_json_path` を持つ。

runtime error code:

```text
input_not_found, invalid_input_json, input_version_mismatch,
empty_generic_evidence, provider_error, model_timeout,
model_response_invalid, retry_exhausted, unexpected_error
```

validation error code:

```text
schema_validation_failed, taxonomy_parent_mismatch,
evidence_unresolved, quote_not_found, page_source_mismatch,
unsupported_entity, unsupported_number, unsupported_causality,
event_formation_incomplete, amount_unit_pair_invalid,
identity_collision, count_reconciliation_failed
```

### 9.3 review queue

`review_item_type` は `document` または `event`。`review_item_id` を主キーとし、document/event、theme、confidence、`review_reasons_json`, `evidence_refs_json`, canonical path、review statusを保持する。`event_id` はキーとして必須だがnullableであり、event itemではnon-null、document itemではnullとする。CSV列順にも `review_item_type` を含める。

low text qualityなどrouting段階のdocument-level `review_only` は、eventもcanonical JSONもなくてもqueueへ1行記録できる。この場合 `review_item_type=document`, `event_id=null`, `canonical_json_path=null` とする。

初期状態は `pending`。review item objectはnullableの `resolved_at_utc`, `reviewer`, `resolution_note` を持ち、初期pending時はいずれもnullとする。運用更新用に `in_review`, `resolved`, `dismissed` を許可し、解決またはdismiss時にこれらへ解決時刻、担当者、判断理由を記録する。

accepted eventについてconfidenceが `0.70` 未満、方向・強度・実績予想区分がunclear、根拠で支えられた対象の正規化候補が複数残る、またはreviewable warningがある場合はevent review対象とする。`needs_human_review=true` と `review_reasons` 非空は同値であり、`review_item_type=event` のqueue行が必ず存在する。

根拠が解決不能、またはentity・数値・方向・対象・因果がunsupportedな候補はvalidation errorであり、accepted eventやreview対象eventにはしない。

### 9.4 report

日次・run-level reportは最低限次を持つ。

- run IDと3種version
- 開始・終了日時
- 入力文書数、canonical文書数、処理済み文書数
- `success`, `no_event_found`, `needs_review`, `failed_validation`, runtime `failed`, `skipped`, `review_only`, `failed_precheck` 文書数
- event数、全review item数、review event数
- status、L1、error code別件数
- 全出力path

件数収支は[11. バリデーション](#11-バリデーション)に従う。

---

## 10. 例

例は説明用にhashを短縮せず24桁で記載する。実装では必ずYAMLのfingerprintから再計算する。

### 10.1 0件: `no_event_found`

```json
{
  "schema_version": "1.0.0",
  "extraction_version": "2026-07-22.001",
  "taxonomy_version": "1.0.0",
  "document_id": "20260722_0001_abcd1234",
  "source_metadata": {
    "source_id": "202607220001",
    "disclosure_date": "2026-07-22",
    "disclosure_time": "15:00",
    "issuer_code": "0001",
    "issuer_name": "Example Semiconductor",
    "title": "コーポレート・ガバナンス報告書",
    "document_url": "https://example.invalid/0001.pdf",
    "document_type": "governance_personnel",
    "issuer_value_chains": null,
    "issuer_value_chain_raw": null
  },
  "input_versions": {
    "preprocessing_contract_reference": "020_prop_candidates/notebook/tdnet_pdf_preprocessing.py@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "preprocessing_artifact_hashes": {
      "document_json": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    },
    "generic_enrichment_schema_version": "1.0.0",
    "generic_enrichment_version": "2026-07-16.001"
  },
  "extraction_provenance": {
    "llm_called": true,
    "provider": "example_provider",
    "model": "example_model",
    "model_version": null,
    "prompt_version": "2026-07-22.001",
    "context_set_version": "2026-07-22.001",
    "temperature": 0,
    "attempt_count": 1,
    "fallback_used": false,
    "token_usage": {"input_tokens": 1200, "output_tokens": 80, "total_tokens": 1280},
    "input_evidence_ids": ["ev_generic_001"],
    "context_hashes": ["sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
    "latency_ms": 830,
    "cost": null
  },
  "extraction_status": "no_event_found",
  "events": [],
  "warnings": [],
  "validation": {
    "status": "passed",
    "errors": [],
    "checked_at_utc": "2026-07-22T06:01:01Z"
  },
  "generated_at_utc": "2026-07-22T06:01:00Z"
}
```

### 10.2 複数イベント・複数財務指標

以下はトップレベル共通部を省略した `events` の例である。1件目は同じHBM需要影響に売上と営業利益が紐づくため、イベントを分割しない。

```json
[
  {
    "event_id": "evt_111111111111111111111111",
    "dedup_key": "dedup_aaaaaaaaaaaaaaaaaaaaaaaa",
    "macro_theme_l1": "end_market_demand",
    "macro_theme_l2": "ai_server_demand",
    "event_direction": "increase",
    "impact_direction": "positive",
    "impact_strength": "high",
    "time_horizon": "current_period",
    "actual_or_forecast": "forecast",
    "impact_scope": "product",
    "impact_mechanism": "volume_up",
    "normalized_summary": "AIサーバー向けHBM需要増加がメモリ製品の販売数量を押し上げる見込み。",
    "semiconductor_value_chain": "memory",
    "semiconductor_value_chain_raw": "メモリ製品",
    "company_segment_raw": "メモリ事業",
    "company_product_raw": "HBM",
    "normalized_segment": "memory",
    "normalized_product_group": "high_bandwidth_memory",
    "device_category": "hbm",
    "device_category_raw": "HBM",
    "technology_node": null,
    "end_market": "ai_server",
    "end_market_raw": "AIサーバー",
    "customer_group": "hyperscalers",
    "region": "global",
    "region_raw": "グローバル",
    "financial_impacts": [
      {
        "financial_metric": "revenue",
        "impact_direction": "positive",
        "amount_value": 12000,
        "amount_unit": "JPY million",
        "period": "FY2026",
        "actual_or_forecast": "forecast",
        "offsetting_factor": null
      },
      {
        "financial_metric": "operating_profit",
        "impact_direction": "positive",
        "amount_value": 3000,
        "amount_unit": "JPY million",
        "period": "FY2026",
        "actual_or_forecast": "forecast",
        "offsetting_factor": "先端パッケージ増産費用"
      }
    ],
    "evidence_refs": [
      {
        "evidence_id": "ev_generic_101",
        "source_type": "block",
        "source_ids": ["block_0042"],
        "page_numbers": [12],
        "quote": "AIサーバー向けHBM需要の増加により、FY2026の売上高は120億円、営業利益は30億円増加する見込みです。"
      }
    ],
    "confidence": 0.94,
    "needs_human_review": false,
    "review_reasons": []
  },
  {
    "event_id": "evt_222222222222222222222222",
    "dedup_key": "dedup_bbbbbbbbbbbbbbbbbbbbbbbb",
    "macro_theme_l1": "geopolitics_export_control",
    "macro_theme_l2": "export_control",
    "event_direction": "tightening",
    "impact_direction": "negative",
    "impact_strength": "medium",
    "time_horizon": "next_period",
    "actual_or_forecast": "forecast",
    "impact_scope": "region",
    "impact_mechanism": "order_decrease",
    "normalized_summary": "輸出規制強化により中国向け装置受注の減少を見込む。",
    "semiconductor_value_chain": "semiconductor_equipment",
    "semiconductor_value_chain_raw": "半導体製造装置",
    "company_segment_raw": "半導体製造装置",
    "company_product_raw": null,
    "normalized_segment": "semiconductor_equipment",
    "normalized_product_group": null,
    "device_category": "equipment",
    "device_category_raw": "半導体製造装置",
    "technology_node": null,
    "end_market": null,
    "end_market_raw": null,
    "customer_group": null,
    "region": "china",
    "region_raw": "中国",
    "financial_impacts": [],
    "evidence_refs": [
      {
        "evidence_id": "ev_generic_102",
        "source_type": "block",
        "source_ids": ["block_0058"],
        "page_numbers": [16],
        "quote": "輸出規制の強化を踏まえ、次期の中国向け半導体製造装置受注は減少を見込んでおります。"
      }
    ],
    "confidence": 0.89,
    "needs_human_review": false,
    "review_reasons": []
  }
]
```

この1件目のCSVでは `financial_impacts_json` に2 objectを完全保存し、単一object convenience列はすべてnullになる。

### 10.3 定性イベント・company-wide

金額や個別対象がなくても、全社影響とmechanismが根拠で明示されれば成立する。

```json
{
  "event_id": "evt_333333333333333333333333",
  "dedup_key": "dedup_cccccccccccccccccccccccc",
  "macro_theme_l1": "fx",
  "macro_theme_l2": "yen_depreciation",
  "event_direction": "increase",
  "impact_direction": "negative",
  "impact_strength": "low",
  "time_horizon": "current_period",
  "actual_or_forecast": "actual",
  "impact_scope": "company_wide",
  "impact_mechanism": "cost_up",
  "normalized_summary": "円安により全社の輸入原材料コストが増加した。",
  "semiconductor_value_chain": null,
  "semiconductor_value_chain_raw": null,
  "company_segment_raw": null,
  "company_product_raw": null,
  "normalized_segment": null,
  "normalized_product_group": null,
  "device_category": null,
  "device_category_raw": null,
  "technology_node": null,
  "end_market": null,
  "end_market_raw": null,
  "customer_group": null,
  "region": null,
  "region_raw": null,
  "financial_impacts": [
    {
      "financial_metric": "operating_profit",
      "impact_direction": "negative",
      "amount_value": null,
      "amount_unit": null,
      "period": "FY2026 Q1",
      "actual_or_forecast": "actual",
      "offsetting_factor": "一部製品の価格改定"
    }
  ],
  "evidence_refs": [
    {
      "evidence_id": "ev_generic_201",
      "source_type": "block",
      "source_ids": ["block_0017"],
      "page_numbers": [5],
      "quote": "円安による輸入原材料コストの増加が全社営業利益を圧迫しましたが、一部製品の価格改定で影響を軽減しました。"
    }
  ],
  "confidence": 0.86,
  "needs_human_review": false,
  "review_reasons": []
}
```

---

## 11. バリデーション

YAMLの `validation_rules` が機械検証の正本である。主要ルールは次のとおり。

### 11.1 schema・taxonomy・identity

1. `schema_version=1.0.0`, `taxonomy_version=1.0.0`、run内の3種versionが一致
2. L2が選択L1の子である
3. `event_id` が文書IDとcanonical fingerprintから再計算可能
4. event配列順、`normalized_summary` の言い換え、evidence列挙順、または `impact_strength` だけを変えてもIDが不変
5. `dedup_key` は別fingerprintで生成
6. 同一文書・同一L1/L2・同一business impactを重複出力しない
7. `financial_impacts` はcanonical化してfingerprintに含める
8. `preprocessing_schema_version` を使わず、contract referenceとartifact hashesで入力を追跡
9. issuer分類は設定または明示根拠に基づき、LLMで補完しない

### 11.2 event成立と根拠

1. event方向、business impact方向、対象scope、mechanism、1〜8件のevidenceが必須
2. `company_wide` 以外はscope対応対象とその根拠が必要
3. evidence ID/source IDが同文書の投入generic evidence集合へ解決
4. quoteが正規化後の根拠本文substring
5. page/source type/source IDがgeneric evidence metadataと一致
6. 未裏付けのentity、数値、期間、方向、因果を出力しない

### 11.3 値とレビュー

1. 金額value/unitは両方nullまたは両方non-null
2. confidenceは `0.0..1.0`
3. confidence `< 0.70` またはaccepted event向けreview policy該当時はevent review必須
4. `needs_human_review=true`、review reason非空、event queue行存在が一致
5. document reviewとevent reviewの件数を分離
6. unresolved evidenceまたはunsupported claimはaccepted eventにしない
7. `llm_called` とprovider/model/temperature/attempt/token/costの条件が一致
8. enum、null、otherの意味がYAMLと一致
9. `semiconductor_value_chain=other` なら `semiconductor_value_chain_raw`、`device_category=other` なら `device_category_raw`、`end_market=other` なら `end_market_raw`、`region=other` なら `region_raw` がnon-null
10. `device_category=null` / `end_market=null` なら対応rawも原則null

### 11.4 status

- `no_event_found` ⇔ `events=[]`
- `success` ⇒ 1件以上かつreview eventなし
- `needs_review` ⇒ accepted review event、またはchunk/document-level warning + review reasonあり。eventは0件以上
- `failed_validation` ⇒ validation errorあり
- runtime失敗 ⇒ canonical/main event行なし、summary `failed`、failed行あり
- chunk部分失敗 ⇒ `partial` を追加せず `needs_review` + canonical warning + document/event review queue reason。検証済みchunkのaccepted eventだけ保持
- routing除外 ⇒ canonicalなしでもsummary `skipped`, `review_only`, `failed_precheck` のいずれかを1行

### 11.5 projection

1. JSONL/CSVは同じcanonical eventからのみ生成。JSONLはrequired envelopeをnative JSONで保持し、CSVはflat projectionとする
2. `*_json` から配列/objectを完全復元可能
3. financial impactsが1件の場合だけconvenience列を設定
4. 0件または複数件ではconvenience列をすべてnull
5. CSV headerがYAML `column_order` と完全一致
6. CSV null、空文字、空配列、boolean、日時、数値encodingがYAMLどおり

### 11.6 件数収支

```text
input_document_count
  = processed_document_count
  + runtime_failed_document_count
  + skipped_document_count
  + review_only_document_count
  + failed_precheck_document_count

canonical_document_count
  = processed_document_count

processed_document_count
  = success_document_count
  + no_event_document_count
  + needs_review_document_count
  + failed_validation_document_count

event_count
  = success/needs_review canonical内の投影可能event総数
  = event JSONL行数
  = event CSV行数

review_item_count
  = review queue行数

review_event_count
  = needs_human_review=true のaccepted event数
  = review_item_type=event のreview queue行数
```

`review_item_count` はdocument itemとevent itemの合計であり、`review_event_count` とは分ける。summaryはroutingされた全入力文書数と一致する。runtime failureはsummary/failedに現れ、`failed_validation` はcanonical/summary/failedに現れる。無効イベントはmain event件数へ含めない。

---

## 12. versionと運用

### 12.1 schema version

Semantic Versioningを使う。

- major: 列・成果物削除、型変更、必須化、既存enumの意味変更、identity規則の非互換変更
- minor: nullable列、成果物、enum値の追加
- patch: 説明、例、互換性を壊さない制約明確化

### 12.2 extraction version

`YYYY-MM-DD.NNN`。prompt、抽出ロジック、context選択、正規化、confidence/review閾値、fallback方針を変えたら更新する。同じ入力と同じversion群の再実行差分は監査対象にする。

### 12.3 taxonomy version

Semantic Versioningを使い、現行値は `1.0.0`。L1/L2親子map、value chain、device、end market、region、mechanism、financial metricの追加・意味変更時に更新する。削除・意味変更はmajor、互換的追加はminor、説明や非互換性のない訂正はpatchとする。

### 12.4 再処理

1. canonical JSONを先に原子的に書く
2. validation通過後にevent JSONL/CSVへ投影
3. summary、failed、review queueを生成
4. daily reportで件数照合
5. 対象日が揃った後にrun-level aggregateを生成し再照合

同じ `document_id` とversion群を再処理する場合、identity対象フィールドとcanonical financial impactsが同じイベントの `event_id` は不変である。要約の言い換えやevidence列挙順だけではIDを変えない。identity対象または財務影響が変わる場合は新IDとなる。旧canonicalを上書きする運用では、run ID、version、context hashをreport・ログに残し、差分追跡可能にする。

### 12.5 人手レビュー

review queueの解決結果をcanonical抽出値へ直接手編集で反映しない。修正レイヤまたは再抽出入力として記録し、誰が、いつ、何を、なぜ変更したかを残す。taxonomy外の明示値は安易に既存enumへ寄せず、raw + `other` として収集し、taxonomy改訂時に再分類する。
