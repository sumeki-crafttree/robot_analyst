# 適時開示インテリジェンス・データパイプライン要件定義書 v0.1

## 目次

1. [目的](#1-目的)
2. [基本アーキテクチャ](#2-基本アーキテクチャ)
3. [対象ソース](#3-対象ソース)
4. [顧客非依存の分類体系](#4-顧客非依存の分類体系)
5. [顧客固有レイヤー](#5-顧客固有レイヤー)
6. [具体例：ニッスイの価格改定開示](#6-具体例ニッスイの価格改定開示)
7. [顧客固有エンリッチ：ニチレイ視点](#7-顧客固有エンリッチニチレイ視点)
8. [エンリッチ済みデータ例](#8-エンリッチ済みデータ例)
9. [データモデル論点：ワイド1行 vs 正規化](#9-データモデル論点ワイド1行-vs-正規化)
10. [推奨方針：Canonical Modelは正規化、Servingは非正規化](#10-推奨方針canonical-modelは正規化servingは非正規化)
11. [LLMとルール処理の責務分離](#11-llmとルール処理の責務分離)
12. [Confidence設計](#12-confidence設計)
13. [Human Review要件](#13-human-review要件)
14. [イベント重複・時系列化](#14-イベント重複時系列化)
15. [MVP時点の推奨パイプライン](#15-mvp時点の推奨パイプライン)
16. [現時点の主要レビュー論点](#16-現時点の主要レビュー論点)
17. [現時点の推奨設計](#17-現時点の推奨設計)

---

## 1. 目的

本データパイプラインは、適時開示・決算短信・決算説明資料などの企業公開情報を取得し、単なる文書検索・要約ではなく、以下の分析可能な構造化データへ変換することを目的とする。

- 外部環境で何が起きたか
- 企業のどの事業にどう影響したか
- 企業がどのような対応を取ったか
- そのイベントが特定顧客企業にとってどの程度重要か
- どのような因果経路で顧客企業へ影響し得るか
- その判断の根拠となる原文はどこか

基本思想は、**公開文書を「企業イベントの分析用Fact」へ変換する**ことである。

---

## 2. 基本アーキテクチャ

データ処理を以下の4レイヤーに分ける。

1. **Extraction**
   - 原文から事実を抽出する
2. **Normalization**
   - バラバラな企業表現を共通分類体系へ変換する
3. **Semantic Enrichment**
   - 外部環境、事業影響、企業アクションを意味的に接続する
4. **Customer-specific Enrichment**
   - 顧客企業固有の事業・バリューチェーンへ関連付ける

概念フロー：

```text
Disclosure / IR Document
↓
Document Classification
↓
Fact Extraction
↓
Event Detection
↓
Normalization
↓
Macro Theme / Impact / Action Enrichment
↓
Customer-independent Event Store
↓
Customer × Event Mapping
↓
Relationship / Relevance / Impact Path
↓
Alerts / Tables / Reports / API
```

---

## 3. 対象ソース

### 3.1 期中の個別開示

主な用途：

- イベント検知
- 転換点検知
- 具体アクション把握
- 実施日・金額・数量の抽出

例：

- 価格改定
- 設備投資
- 新拠点
- 生産能力増減
- 工場停止
- M&A
- 事業撤退
- 災害・事故
- 業績予想修正
- サプライチェーン障害

### 3.2 四半期決算資料・決算説明資料

主な用途：

- 定点観測
- 業績変動要因の分解
- マクロ環境の影響把握
- 対応方針・見通し
- セグメント・地域別変化
- 定量的な利益影響

例：

```text
原材料価格上昇
↓
利益率低下
↓
価格改定を推進
↓
翌四半期に採算改善
```

### 3.3 ソースごとの扱い

四半期資料と期中開示は同じイベントストアへ格納可能とするが、`source_type` を必須項目として保持する。

例：

- `quarterly_earnings`
- `earnings_presentation`
- `forecast_revision`
- `timely_disclosure`
- `capex_announcement`
- `restructuring`
- `incident`

---

## 4. 顧客非依存の分類体系

### 4.1 dim_macro_theme

「外部環境で何が起きたか」を表す。

- `input_cost`
- `fx`
- `interest_rate`
- `inflation`
- `labor_market`
- `logistics`
- `regional_demand`
- `end_market_demand`
- `consumer_behavior`
- `trade_policy`
- `geopolitics`
- `industry_supply_demand`
- `regulation`
- `asset_price`
- `weather_natural_disaster`

### 4.2 dim_impact_mechanism

「外部変化が企業にどう効いたか」を表す。

#### cost
- `raw_material_cost_up`
- `energy_cost_up`
- `labor_cost_up`
- `logistics_cost_up`
- `packaging_cost_up`
- `financing_cost_up`
- `development_cost_up`

#### demand
- `volume_up`
- `volume_down`
- `traffic_up`
- `traffic_down`
- `order_up`
- `order_down`

#### pricing
- `selling_price_up`
- `selling_price_down`
- `average_ticket_up`
- `average_ticket_down`

#### margin
- `margin_up`
- `margin_down`

#### inventory
- `inventory_build`
- `inventory_reduction`

#### supply
- `supply_constraint`
- `production_adjustment`
- `capacity_expansion`
- `capacity_reduction`

#### capital
- `capex_increase`
- `capex_delay`
- `working_capital_increase`
- `working_capital_decrease`

#### asset
- `asset_value_up`
- `asset_value_down`

### 4.3 dim_company_action

企業が取った、または取ろうとしている対応。

- `price_increase`
- `price_decrease`
- `cost_reduction`
- `supplier_diversification`
- `alternative_material`
- `inventory_build`
- `inventory_reduction`
- `production_increase`
- `production_reduction`
- `capacity_expansion`
- `facility_opening`
- `facility_closure`
- `capex_increase`
- `capex_delay`
- `automation`
- `network_restructuring`
- `product_mix_shift`
- `market_entry`
- `market_exit`
- `acquisition`
- `divestiture`
- `service_launch`

### 4.4 dim_action_status

- `considering`
- `planned`
- `announced`
- `in_progress`
- `completed`
- `cancelled`

### 4.5 dim_end_market

- `automotive`
- `electronics`
- `semiconductor`
- `construction`
- `housing`
- `real_estate`
- `packaging`
- `food_manufacturing`
- `food_retail`
- `general_retail`
- `foodservice`
- `consumer_goods`
- `healthcare`
- `pharma`
- `water_treatment`
- `logistics`
- `energy`
- `industrial_equipment`
- `agriculture`
- `tourism`
- `hospitality`
- `public_sector`

### 4.6 dim_region

- `global`
- `japan`
- `north_america`
- `europe`
- `china`
- `southeast_asia`
- `india`
- `middle_east`
- `oceania`
- `latin_america`
- `africa`
- `other`
- `unknown`

---

## 5. 顧客固有レイヤー

### 5.1 dim_relationship_type

開示企業と顧客企業の関係を表す。

- `peer_direct`
- `peer_adjacent`
- `supplier_direct`
- `supplier_upstream`
- `supplier_signal`
- `customer_direct`
- `customer_signal`
- `logistics_partner`
- `distribution_partner`
- `substitute`
- `complementor`
- `industry_indicator`
- `macro_proxy`

1企業に複数のrelationshipを許容する。

### 5.2 顧客固有属性

`event × customer` 単位で以下を保持する。

- `customer_business_area`
- `relationship_type`
- `relationship_strength`
- `relevance_score`
- `impact_path`
- `expected_direction`
- `leading_lagging_type`
- `relevance_confidence`
- `impact_inference_confidence`

---

## 6. 具体例：ニッスイの価格改定開示

### 6.1 生データ

例：ニッスイが2026年6月1日に発表した冷凍食品等の価格改定。

```json
{
  "company_name": "ニッスイ",
  "ticker": "1332",
  "disclosure_date": "2026-06-01",
  "title": "家庭用冷凍食品・家庭用加工食品・業務用冷凍食品の一部商品の出荷価格改定",
  "body_text": "原材料の価格高騰、国内外での人件費の増加、燃料・包装資材費および物流費の上昇が続いています。..."
}
```

この状態では全文検索は可能だが、横断集計・比較・アラートには利用しづらい。

---

### 6.2 Document Classification

```json
{
  "source_type": "timely_disclosure",
  "event_type": "price_revision",
  "event_date": "2026-06-01",
  "effective_date": "2026-09-01"
}
```

---

### 6.3 Fact Extraction

原文から、解釈を最小限にして事実を抽出する。

```json
{
  "reasons": [
    "原材料価格高騰",
    "国内外での人件費増加",
    "燃料費上昇",
    "包装資材費上昇",
    "物流費上昇"
  ],
  "target_products": [
    {
      "category": "家庭用冷凍食品",
      "price_change_min_pct": 2,
      "price_change_max_pct": 17
    },
    {
      "category": "家庭用加工食品",
      "price_change_min_pct": 5,
      "price_change_max_pct": 17
    },
    {
      "category": "業務用冷凍食品",
      "price_change_min_pct": 2,
      "price_change_max_pct": 30
    }
  ]
}
```

---

### 6.4 Macro Theme Normalization

原文表現を共通分類へ正規化する。

| 原文 | macro_theme | subtheme候補 |
|---|---|---|
| 原材料価格高騰 | `input_cost` | `raw_material` |
| 人件費増加 | `labor_market` | `labor_cost` |
| 燃料費上昇 | `input_cost` | `fuel` |
| 包装資材費上昇 | `input_cost` | `packaging` |
| 物流費上昇 | `logistics` | `freight_cost` |

---

### 6.5 Impact Mechanism Enrichment

```json
[
  "raw_material_cost_up",
  "labor_cost_up",
  "energy_cost_up",
  "packaging_cost_up",
  "logistics_cost_up"
]
```

`margin_down` のように原文から直接確認できないものは、推論として別confidenceを持つ。

---

### 6.6 Company Action Enrichment

```json
{
  "company_action": "price_increase",
  "action_status": "announced",
  "effective_date": "2026-09-01"
}
```

商品カテゴリー別には以下の定量値を保持する。

```text
家庭用冷凍食品      +2〜17%
家庭用加工食品      +5〜17%
業務用冷凍食品      +2〜30%
```

---

### 6.7 End Market / Region Enrichment

商品カテゴリーと用途マスタを用いて補完する。

```json
{
  "region": "japan",
  "end_markets": [
    "food_retail",
    "foodservice"
  ]
}
```

これは原文直接抽出ではなく、商品・用途マスタによるエンリッチである。

---

## 7. 顧客固有エンリッチ：ニチレイ視点

ニッスイのイベントにニチレイのコンテキストを掛け合わせる。

### 7.1 Relationship Mapping

```json
{
  "customer": "ニチレイ",
  "relationship_type": [
    "peer_direct",
    "supplier_signal"
  ],
  "relationship_strength": "high"
}
```

### 7.2 Customer Business Mapping

```json
{
  "customer_business_area": [
    "家庭用冷凍食品",
    "業務用冷凍食品"
  ],
  "relevance_score": 0.95
}
```

### 7.3 Impact Path

```text
原材料・人件費・物流費上昇
↓
ニッスイの冷凍食品原価上昇
↓
競合が2〜30%の価格改定を発表
↓
冷凍食品業界で価格転嫁が進行している可能性
↓
ニチレイの価格政策・採算にも示唆
```

構造化例：

```json
{
  "signal": "peer_price_increase",
  "target": "nichirei_frozen_food",
  "expected_direction": "positive_pricing_power",
  "leading_lagging_type": "leading_or_contemporaneous",
  "impact_inference_confidence": 0.73
}
```

---

## 8. エンリッチ済みデータ例

```json
{
  "event_id": "evt_20260601_nissui_price_001",
  "company_id": "1332",
  "source_type": "timely_disclosure",
  "event_type": "price_revision",
  "event_date": "2026-06-01",
  "effective_date": "2026-09-01",

  "macro_themes": [
    "input_cost",
    "labor_market",
    "logistics"
  ],

  "impact_mechanisms": [
    "raw_material_cost_up",
    "labor_cost_up",
    "energy_cost_up",
    "packaging_cost_up",
    "logistics_cost_up"
  ],

  "company_action": "price_increase",
  "action_status": "announced",

  "end_markets": [
    "food_retail",
    "foodservice"
  ],

  "region": "japan",

  "customer_context": {
    "customer": "ニチレイ",
    "relationship_type": "peer_direct",
    "customer_business_area": "冷凍食品",
    "relevance_score": 0.95,
    "impact_path": "競合原価上昇→競合値上げ→業界価格転嫁進展→ニチレイの価格政策への示唆"
  },

  "evidence": {
    "evidence_text": "原材料の価格高騰、国内外での人件費の増加、燃料・包装資材費および物流費の上昇が続いています。",
    "extraction_confidence": 0.98,
    "impact_inference_confidence": 0.73
  }
}
```

---

## 9. データモデル論点：ワイド1行 vs 正規化

### 9.1 案A：非正規化したワイド1行

例：

```text
event_id
company
macro_theme_1
macro_theme_2
macro_theme_3
impact_1
impact_2
impact_3
company_action
end_market_1
end_market_2
...
```

#### メリット

- PoCで実装しやすい
- BI・CSV出力が容易
- LLMのJSON出力をそのまま保存しやすい
- 1レコードを人が理解しやすい

#### デメリット

- macro_themeやimpactの複数付与で列が増殖する
- 配列型を多用するとSQL集計が複雑になる
- taxonomy変更への追従が難しい
- 1イベントに複数商品・地域・アクションがある場合に破綻しやすい

---

### 9.2 案B：正規化

推奨候補：

```text
fact_event
bridge_event_macro_theme
bridge_event_impact
bridge_event_end_market
bridge_event_action
bridge_event_customer
```

#### fact_event

```text
event_id
company_id
disclosure_id
source_type
event_type
event_date
effective_date
summary
evidence_text
source_url
confidence
```

#### bridge_event_macro_theme

```text
event_id
macro_theme_id
macro_subtheme_id
confidence
```

#### bridge_event_impact

```text
event_id
impact_mechanism_id
direction
financial_metric
quantitative_value
confidence
```

#### bridge_event_action

```text
event_id
company_action_id
action_status_id
effective_date
action_scope
quantitative_value
quantitative_unit
```

#### bridge_event_customer

```text
event_id
customer_id
relationship_type_id
customer_business_area
relevance_score
impact_path
expected_direction
leading_lagging_type
relevance_confidence
```

#### メリット

- 多対多関係を自然に扱える
- taxonomyの変更に強い
- イベント時系列を作りやすい
- 顧客非依存データと顧客固有データを分離できる
- API・分析・機械学習への展開がしやすい

#### デメリット

- 実装が複雑
- JOINが増える
- 人間が直接見るには扱いにくい
- 初期PoCにはややオーバーエンジニアリングになり得る

---

## 10. 推奨方針：Canonical Modelは正規化、Servingは非正規化

現時点では以下を推奨する。

### Storage / Canonical Layer

正規化する。

```text
fact_event
+
bridge_event_macro_theme
+
bridge_event_impact
+
bridge_event_action
+
bridge_event_end_market
+
bridge_event_customer
```

### Serving / BI / API Layer

用途別に非正規化Viewを作る。

例：

- `mart_peer_event_watch`
- `mart_customer_alert`
- `mart_macro_theme_summary`
- `mart_company_timeline`

これにより、

**保存モデルは壊れにくく、利用側は使いやすい**

状態を狙う。

---

## 11. LLMとルール処理の責務分離

### LLMが得意な処理

- 文書の意味理解
- イベント抽出
- 原因・影響・対応の識別
- 原文とtaxonomyの意味的マッピング
- evidence span抽出
- customer relevanceの推論
- impact path候補生成

### ルール・コードで担保したい処理

- ticker / company ID解決
- 日付正規化
- 数値・単位正規化
- taxonomy code検証
- action_status整合性
- percentage / JPY / quantity parser
- source URL管理
- deduplication
- schema validation
- foreign key整合性

### 方針

**LLMに最終DBレコードを直接自由生成させない。**

LLMは候補値と根拠を返し、後段でschema validation・master lookup・rule validationを行う。

---

## 12. Confidence設計

最低でも以下を分離する。

### extraction_confidence

原文からその情報が正しく抽出できている確度。

例：

```text
「9月1日から値上げ」 → 0.99
```

### normalization_confidence

原文表現をtaxonomyへ正しく分類できている確度。

例：

```text
「包装資材費上昇」 → input_cost / packaging → 0.97
```

### relevance_confidence

顧客企業との関連性判定の確度。

例：

```text
ニッスイ価格改定 → ニチレイ冷凍食品 → 0.95
```

### impact_inference_confidence

顧客への具体的な影響方向を推論した確度。

例：

```text
競合値上げ → ニチレイの価格転嫁余地拡大 → 0.73
```

事実抽出のconfidenceと推論confidenceを混ぜないことを必須とする。

---

## 13. Human Review要件

重要度またはconfidenceに応じてHuman Reviewを入れる余地を持つ。

例：

```text
relevance_score >= 0.8
AND
impact_inference_confidence < 0.7
→ review queue
```

レビュー対象候補：

- 新しいtaxonomy候補
- 未知の商品カテゴリ
- 高importance / 低confidenceイベント
- 複数解釈が可能な開示
- 顧客固有impact pathの重要イベント

Human correctionは学習・few-shot・評価データとして保存する。

---

## 14. イベント重複・時系列化

同一事象が複数ソースに現れることを前提とする。

例：

```text
Q1決算説明：
原材料高、値上げを検討
↓
6月期中開示：
9月から値上げを正式発表
↓
Q2決算説明：
価格転嫁が進展
```

これらを完全に別イベントとして扱うだけでなく、必要に応じて

```text
event_cluster_id
```

を付与して、一連の企業対応として追跡可能にする。

---

## 15. MVP時点の推奨パイプライン

```text
1. Disclosure ingestion
2. Text extraction
3. Document classification
4. Candidate event extraction
5. Fact extraction
6. Taxonomy classification
7. Impact mechanism extraction
8. Company action extraction
9. Quantitative data normalization
10. Evidence validation
11. Customer-independent event persistence
12. Customer relationship lookup
13. Customer relevance scoring
14. Impact path generation
15. Confidence scoring
16. Human review where required
17. Serving mart generation
```

---

## 16. 現時点の主要レビュー論点

1. 1開示を何個の`event`に分割するか
2. `event`と`impact`の粒度をどこで切るか
3. macro themeの複数付与を常に許可するか
4. impact mechanismを多対多で保持するか
5. company actionをイベント本体に置くかbridgeにするか
6. 商品カテゴリーを独立dimにするか
7. `end_market`と商品用途の境界をどうするか
8. `impact_path`を自然言語のまま保持するか、ノード・エッジで構造化するか
9. 同一事象の複数ソースを`event_cluster`でまとめるか
10. Canonical Layerをどこまで正規化するか
11. PoC段階でどこまでHuman Reviewを入れるか
12. 顧客固有relevanceをルール・LLM・学習モデルのどこまでで担うか
13. taxonomy更新時のversioningをどうするか
14. 過去データをtaxonomy変更時に再分類するか
15. Serving martの用途別非正規化方針をどうするか

---

## 17. 現時点の推奨設計

MVPでは、以下を基本方針とする。

- 生文書は必ず保存する
- evidence spanを必ず保持する
- 顧客非依存イベントを先に作る
- 顧客固有relevanceは別レイヤーで付与する
- Canonical Modelはある程度正規化する
- BI/API向けには非正規化Martを提供する
- 事実と推論のconfidenceを分離する
- LLM出力は必ずschema validationを通す
- taxonomyはversion管理可能にする
- Human correctionを評価・改善データとして蓄積する

最終的に目指す状態は、単なる文書DBではなく、

```text
Company
×
Event
×
Macro Theme
×
Impact
×
Action
×
End Market
×
Customer Relationship
```

を時系列で追跡できる**企業外部環境インテリジェンス基盤**である。
