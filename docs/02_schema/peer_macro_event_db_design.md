# 適時開示を用いた同業マクロ影響イベントDB設計

## 背景

クラレを想定顧客として、国内化学・素材企業の適時開示から、原燃料・為替・地域需要・価格転嫁・設備投資・在庫・地政学などの変化が、どの会社・どの事業にどう出ているかを比較可能なテーブルにする。

まずは適時開示だけをデータソースに絞る。アウトプットの前段階として作るべきは、単なる「開示資料DB」ではなく、**同業マクロ影響イベントDB**である。

つまり、1つの適時開示PDFを1レコードとして保存するだけでは弱く、そこから以下を切り出す。

> どの会社が、いつ、どのマクロテーマについて、どの事業・地域・財務項目への影響を開示したか

---

## 1. 全体像：最初に作るべきテーブル群

MVPでは、最初は以下の5テーブルで十分。

| テーブル | 目的 |
|---|---|
| `tdnet_disclosures` | 適時開示の原本メタデータ |
| `disclosure_relevance_classification` | クラレ視点で読む価値があるかの分類 |
| `macro_theme_events` | 原燃料・為替・地域需要などのイベント抽出 |
| `business_impact_mentions` | どの事業・製品・地域に影響したか |
| `financial_impact_mentions` | 売上・利益・在庫・CFなど財務影響の抽出 |

最初から正規化しすぎると重いので、実装上は1つのワイドテーブルから始めてもよい。  
ただし、概念上はこの5つに分けると設計しやすい。

---

## 2. `tdnet_disclosures`：適時開示の原本テーブル

開示1件につき1行。

| カラム | 型 | 例 | 用途 |
|---|---:|---|---|
| `disclosure_id` | string | `20260601_3405_xxxx` | 一意ID |
| `disclosure_date` | date | `2026-06-01` | 開示日 |
| `disclosure_time` | time | `15:00` | 開示時刻 |
| `ticker` | string | `3405` | 証券コード |
| `company_name` | string | `株式会社クラレ` | 会社名 |
| `peer_group` | string | `specialty_chemicals` | 同業グループ |
| `title` | string | `2026年12月期 第1四半期決算短信` | 開示タイトル |
| `tdnet_category_raw` | string | `決算短信` | TDnet上の分類 |
| `document_type` | enum | `earnings_release`, `revision`, `presentation`, `capex`, `impairment`, `ma`, `other` | 自前分類 |
| `pdf_url` | string | URL | 原本リンク |
| `text_extracted` | bool | true | 本文抽出済みか |
| `has_tables` | bool | true | 表あり |
| `language` | enum | `ja`, `en`, `both` | 言語 |
| `created_at` | timestamp |  | 取得日時 |

ここではまだ高度な分析はしない。  
ただし、`document_type` は重要。

特に見るべき適時開示タイプは以下。

| document_type | 優先度 | 理由 |
|---|---:|---|
| `earnings_release` | 高 | 決算短信。業績変動要因が出る |
| `earnings_presentation` | 高 | 決算説明資料。価格・数量・原料・為替の分解が出やすい |
| `forecast_revision` | 高 | マクロ影響が明示されやすい |
| `business_plan` | 中 | 中計・事業方針 |
| `capex` | 中 | 設備投資・増産・撤退 |
| `impairment` | 中 | 需要減速・採算悪化のサイン |
| `ma_restructuring` | 中 | 事業ポートフォリオ変化 |
| `dividend_buyback` | 低 | クラレ視点のマクロ影響にはやや遠い |
| `governance` | 低 | 原則除外 |

---

## 3. `disclosure_relevance_classification`：読む価値の判定テーブル

適時開示はノイズが多いため、まずクラレ視点で読む価値をスコアリングする。

| カラム | 型 | 例 |
|---|---:|---|
| `disclosure_id` | string | `...` |
| `relevance_score` | int | `85` |
| `relevance_level` | enum | `high`, `medium`, `low`, `exclude` |
| `relevance_reason` | text | `原燃料価格上昇と価格改定に言及。クラレのVinyl Acetate事業と比較可能。` |
| `is_peer_relevant` | bool | true |
| `is_macro_relevant` | bool | true |
| `is_business_impact_relevant` | bool | true |
| `is_financial_impact_relevant` | bool | true |
| `recommended_action` | enum | `alert`, `include_weekly`, `include_quarterly`, `archive_only`, `exclude` |

ここでの肝は、**開示の重要性ではなく、クラレにとっての比較価値**で評価すること。

たとえば、同業他社の自己株買いは株式市場的には重要でも、クラレの事業影響分析には不要かもしれない。  
一方で、小さな業績予想修正でも「欧州需要低迷」「原燃料価格上昇」「価格転嫁遅れ」が理由なら重要度は高い。

---

## 4. `macro_theme_events`：マクロテーマ別イベントテーブル

ここが中核。  
開示1件から複数イベントを抽出する。

たとえば1つの決算説明資料に、以下が書かれていたら5行に分ける。

- 原燃料価格上昇
- 欧州需要低迷
- 円安効果
- 価格改定の進展
- 中国向け在庫調整

| カラム | 型 | 例 |
|---|---:|---|
| `event_id` | string | `evt_000001` |
| `disclosure_id` | string | `...` |
| `ticker` | string | `4183` |
| `company_name` | string | `三井化学` |
| `event_date` | date | `2026-05-10` |
| `macro_theme_l1` | enum | `input_cost`, `fx`, `regional_demand`, `price_pass_through`, `inventory`, `capex`, `geopolitics` |
| `macro_theme_l2` | enum | `naphtha`, `natural_gas`, `yen_depreciation`, `china_slowdown`, `europe_weakness`, `tariff`, etc. |
| `event_direction` | enum | `positive`, `negative`, `mixed`, `neutral`, `unclear` |
| `impact_strength` | enum | `high`, `medium`, `low`, `unclear` |
| `time_horizon` | enum | `current_quarter`, `next_quarter`, `full_year`, `medium_term`, `unclear` |
| `evidence_text` | text | 原文該当箇所 |
| `normalized_summary` | text | `原燃料価格上昇により機能材料セグメントの利益を押し下げ。価格改定で一部相殺。` |
| `confidence` | float | `0.86` |

### `macro_theme_l1` 候補

| macro_theme_l1 | 意味 |
|---|---|
| `input_cost` | 原材料・燃料・エネルギー価格 |
| `fx` | 為替 |
| `regional_demand` | 地域別需要 |
| `price_pass_through` | 価格転嫁・値上げ |
| `inventory` | 在庫調整・棚卸評価 |
| `capex_supply` | 設備投資・供給能力 |
| `geopolitics_trade` | 地政学・関税・輸出規制 |
| `logistics` | 物流費・海上輸送・納期 |
| `end_market_demand` | 自動車・建築・電子材料など最終需要 |
| `financial_conditions` | 金利・資金調達 |

クラレ想定なら、`macro_theme_l2` がかなり重要。

| l1 | l2候補 |
|---|---|
| `input_cost` | `naphtha`, `crude_oil`, `natural_gas_us`, `natural_gas_eu`, `electricity`, `coal`, `benzene`, `butadiene`, `methanol`, `acetic_acid` |
| `fx` | `usd_jpy`, `eur_jpy`, `cny_jpy`, `translation_effect`, `transaction_effect` |
| `regional_demand` | `china_slowdown`, `europe_weakness`, `us_recovery`, `asia_demand`, `japan_domestic` |
| `price_pass_through` | `price_increase`, `formula_pricing`, `lagged_pass_through`, `failed_pass_through` |
| `inventory` | `customer_destocking`, `inventory_valuation`, `channel_inventory`, `production_adjustment` |
| `capex_supply` | `capacity_expansion`, `new_plant`, `shutdown`, `maintenance`, `supply_shortage`, `oversupply` |
| `geopolitics_trade` | `tariff`, `export_control`, `middle_east`, `red_sea`, `china_us_tension`, `economic_security` |
| `end_market_demand` | `automotive`, `electronics`, `semiconductor`, `packaging`, `construction`, `water_treatment`, `medical` |

---

## 5. `business_impact_mentions`：事業・製品・地域への影響

マクロイベントだけだとまだ抽象的。  
クラレ向けには、**どの製品・用途に関係するか**まで落とす必要がある。

| カラム | 型 | 例 |
|---|---:|---|
| `business_impact_id` | string | `biz_000001` |
| `event_id` | string | `evt_000001` |
| `company_segment_raw` | string | `機能材料セグメント` |
| `company_product_raw` | string | `高機能フィルム` |
| `normalized_segment` | string | `functional_materials` |
| `normalized_product_group` | string | `film_materials` |
| `kuraray_relevance_area` | enum | `vinyl_acetate`, `isoprene`, `functional_materials`, `fibers_textiles`, `trading`, `unknown` |
| `end_market` | enum | `automotive`, `electronics`, `packaging`, `construction`, `water_treatment`, `medical`, `consumer_goods`, `other` |
| `region` | enum | `japan`, `north_america`, `europe`, `china`, `asia_ex_china`, `global`, `unknown` |
| `impact_mechanism` | enum | `cost_up`, `price_up`, `volume_down`, `volume_up`, `margin_down`, `margin_up`, `supply_constraint`, `inventory_adjustment`, `capex_change` |
| `impact_description` | text | `欧州建築向け需要低迷により高機能フィルムの販売数量が減少。` |

ここで重要なのは、他社のセグメント名をそのまま持つだけでなく、**クラレ視点の正規化軸**を持つこと。

たとえば、他社の「モビリティ材料」「機能樹脂」「高機能プラスチック」は名称が違っても、クラレ視点では以下のように寄せる必要がある。

- `automotive`
- `functional_materials`
- `isoprene_related`
- `vinyl_acetate_adjacent`

---

## 6. `financial_impact_mentions`：財務影響テーブル

ここは、レポートやアラートの説得力に直結する。

| カラム | 型 | 例 |
|---|---:|---|
| `financial_impact_id` | string | `fin_000001` |
| `event_id` | string | `evt_000001` |
| `financial_metric` | enum | `sales`, `operating_profit`, `ebitda`, `ordinary_profit`, `net_income`, `gross_margin`, `inventory`, `cash_flow`, `capex`, `roic` |
| `impact_direction` | enum | `increase`, `decrease`, `mixed`, `unclear` |
| `amount_value` | numeric | `-3500` |
| `amount_unit` | enum | `JPY_mn`, `JPY_bn`, `percent`, `bps`, `unknown` |
| `period` | string | `FY2026_Q1` |
| `is_actual_or_forecast` | enum | `actual`, `forecast`, `plan`, `qualitative` |
| `impact_driver` | string | `原燃料価格上昇` |
| `offsetting_factor` | string | `価格改定により一部相殺` |
| `evidence_text` | text | 原文該当箇所 |
| `confidence` | float | `0.78` |

最初から金額を全部抜けるとは限らない。  
そのため、`amount_value` が空でも、`impact_direction` と `financial_metric` が入っているだけで価値がある。

例：

| financial_metric | impact_direction | impact_driver | offsetting_factor |
|---|---|---|---|
| `operating_profit` | `decrease` | 原燃料価格上昇 | 価格改定 |
| `sales` | `decrease` | 中国需要鈍化 | 高付加価値品の販売増 |
| `inventory` | `increase` | 需要減速 | 生産調整 |
| `gross_margin` | `increase` | 価格改定 | 数量減 |

---

## 7. 最初はワイドテーブルでもよい

MVPでは、以下のような1枚のテーブルにしてもよい。  
初期のPoCではこの方が見やすい。

### `peer_macro_event_table`

| カラム | 例 |
|---|---|
| `event_id` | `evt_000001` |
| `disclosure_date` | `2026-05-10` |
| `ticker` | `4183` |
| `company_name` | `三井化学` |
| `title` | `2026年3月期 決算説明資料` |
| `document_type` | `earnings_presentation` |
| `macro_theme_l1` | `input_cost` |
| `macro_theme_l2` | `naphtha` |
| `event_direction` | `negative` |
| `impact_strength` | `medium` |
| `segment_raw` | `機能材料` |
| `product_raw` | `フィルム・シート` |
| `kuraray_relevance_area` | `vinyl_acetate` |
| `end_market` | `packaging` |
| `region` | `global` |
| `impact_mechanism` | `cost_up` |
| `financial_metric` | `operating_profit` |
| `impact_direction` | `decrease` |
| `amount_value` | null |
| `amount_unit` | null |
| `offsetting_factor` | `価格改定` |
| `normalized_summary` | `ナフサ由来の原燃料価格上昇が機能材料の採算を押し下げたが、価格改定で一部相殺。` |
| `evidence_text` | 原文抜粋 |
| `source_url` | PDF URL |
| `page_number` | `12` |
| `confidence` | `0.84` |
| `recommended_output` | `weekly_alert` |

これが作れれば、そのまま以下に使える。

- 週次アラート
- 四半期レポート
- テーマ別集計
- 同業比較
- 企業別タイムライン
- クラレ事業別リスクマップ

---

## 8. テーマ分類の設計

今回のテーマは、クラレ向けなら以下の分類がよい。

### `macro_theme_l1 / l2`

| l1 | l2 | 見る理由 |
|---|---|---|
| `input_cost` | `naphtha` | Vinyl Acetate、樹脂、フィルム、化学品に波及 |
| `input_cost` | `natural_gas` | 米欧拠点のエネルギーコスト |
| `input_cost` | `electricity` | 製造コスト、欧州拠点リスク |
| `input_cost` | `raw_material_general` | 汎用的な原材料高 |
| `fx` | `usd_jpy` | 海外売上・原料調達・換算影響 |
| `fx` | `eur_jpy` | 欧州売上・欧州コスト |
| `regional_demand` | `china_slowdown` | 中国向け素材・自動車・電子材料需要 |
| `regional_demand` | `europe_weakness` | 建築、自動車、包装需要 |
| `regional_demand` | `us_growth` | 米国事業・活性炭・水処理など |
| `price_pass_through` | `price_increase` | 原料高をどこまで転嫁できているか |
| `price_pass_through` | `pass_through_lag` | 利益率悪化の先行指標 |
| `inventory` | `destocking` | 顧客在庫調整、数量減 |
| `inventory` | `valuation_gain_loss` | 原料価格変動による棚卸影響 |
| `capex_supply` | `capacity_expansion` | 将来の供給過剰・競争激化 |
| `capex_supply` | `shutdown_restructuring` | 需給改善・競合撤退 |
| `geopolitics_trade` | `tariff` | 米中・米国関税政策 |
| `geopolitics_trade` | `middle_east` | 原油・ナフサ・物流 |
| `geopolitics_trade` | `export_control` | 高機能材料・電子材料 |
| `logistics` | `ocean_freight` | 輸送費・納期・在庫積み増し |
| `end_market` | `automotive` | PVB、機能材料、樹脂 |
| `end_market` | `electronics` | 光学フィルム、電子材料 |
| `end_market` | `packaging` | EVAL、フィルム、樹脂 |
| `end_market` | `construction` | PVB、建材、樹脂 |
| `end_market` | `water_treatment` | 活性炭等 |

---

## 9. クラレ視点の `kuraray_relevance_area`

同業開示を読むとき、クラレのどの領域に関係するかを必ず付与する。

| kuraray_relevance_area | 含めるもの |
|---|---|
| `vinyl_acetate` | PVA、PVB、EVAL、光学用PVAフィルム |
| `isoprene` | イソプレン、エラストマー、GENESTAR関連 |
| `functional_materials` | メタクリル、メディカル、活性炭等 |
| `fibers_textiles` | 人工皮革、繊維、不織布等 |
| `trading` | 商社機能、調達・販売チャネル |
| `corporate_fx_finance` | 為替、金利、全社財務影響 |
| `unknown_or_indirect` | 間接的・判定困難 |

これを入れると、後で以下が可能になる。

- 「Vinyl Acetateに関係する同業開示だけ見たい」
- 「EVAL/包装用途に近いイベントだけ集計したい」
- 「欧州建築需要に関係する同業コメントを横比較したい」

---

## 10. 具体的なレコード例

仮の例だが、最終的に欲しい1行は以下のようなもの。

| 項目 | 値 |
|---|---|
| company | 東洋紡 |
| disclosure_date | 2026-05-xx |
| document_type | 決算説明資料 |
| macro_theme_l1 | `input_cost` |
| macro_theme_l2 | `raw_material_general` |
| kuraray_relevance_area | `vinyl_acetate` |
| end_market | `packaging` |
| region | `japan/global` |
| impact_mechanism | `cost_up` |
| financial_metric | `operating_profit` |
| impact_direction | `decrease` |
| offsetting_factor | `price_increase` |
| summary | 包装用フィルムで原材料価格上昇が採算を圧迫したが、価格改定で一部相殺。 |
| recommended_output | `weekly_alert` / `quarterly_report` |

もう1つの例。

| 項目 | 値 |
|---|---|
| company | 三菱ケミカルグループ |
| disclosure_date | 2026-05-xx |
| document_type | 業績予想修正 |
| macro_theme_l1 | `regional_demand` |
| macro_theme_l2 | `china_slowdown` |
| kuraray_relevance_area | `functional_materials` |
| end_market | `electronics` |
| region | `china` |
| impact_mechanism | `volume_down` |
| financial_metric | `sales` / `operating_profit` |
| impact_direction | `decrease` |
| summary | 中国向け高機能材料需要の低迷により販売数量が減少。 |
| recommended_output | `weekly_alert` |

---

## 11. レポート前段階としての集計ビュー

イベントテーブルができたら、レポートを書く前に以下のビューを作る。

### A. テーマ別イベント集計

| theme | 直近週 | 直近月 | 前四半期比 | 主な企業 | 方向感 |
|---|---:|---:|---:|---|---|
| 原燃料高 | 5件 | 18件 | +6件 | 東洋紡、三井化学、DIC | negative |
| 価格転嫁 | 4件 | 12件 | +2件 | 東ソー、カネカ | mixed |
| 中国需要鈍化 | 3件 | 9件 | +5件 | 旭化成、三菱ケミカル | negative |
| 設備増強 | 1件 | 4件 | -1件 | 住友化学 | mixed |

### B. クラレ事業別リスクビュー

| kuraray_area | 関連イベント数 | 主なテーマ | 影響方向 | 要注意企業 |
|---|---:|---|---|---|
| Vinyl Acetate | 12 | ナフサ、包装需要、価格転嫁 | mixed/negative | 東洋紡、DIC、三井化学 |
| Isoprene | 6 | 自動車需要、原料、在庫調整 | negative | 旭化成、JSR |
| Functional Materials | 10 | 電子材料、中国、為替 | mixed | 三菱ケミカル、東レ |
| Fibers/Textiles | 5 | 衣料・合繊需要、原料高 | negative | 東レ、帝人、ユニチカ |

### C. 企業別タイムライン

| company | date | event | theme | impact | relevance |
|---|---|---|---|---|---|
| 東洋紡 | 2026-05-xx | 包装フィルムの価格改定進展 | 価格転嫁 | positive | high |
| DIC | 2026-05-xx | 原料価格上昇で利益圧迫 | 原燃料 | negative | high |
| 東レ | 2026-05-xx | 中国・欧州向け需要弱含み | 地域需要 | negative | medium |

### D. アラート候補リスト

| priority | company | disclosure | why_alert | kuraray_area | action |
|---:|---|---|---|---|---|
| 1 | DIC | 決算説明資料 | 原燃料高と価格転嫁遅れが明示され、Vinyl Acetate周辺に示唆 | Vinyl Acetate | 経営企画・事業部に共有 |
| 2 | 東レ | 決算短信 | 中国向け機能材需要の弱さに言及 | Functional Materials | 四半期レポートに反映 |
| 3 | 東洋紡 | 決算説明資料 | 包装フィルムの価格改定進展 | Vinyl Acetate/EVAL | 価格転嫁ベンチマークに追加 |

---

## 12. 最初のMVPスコープ

初期は以下のように切るのが現実的。

### 対象企業

クラレを起点に、国内化学・素材15社。

例：

- 三菱ケミカルグループ
- 住友化学
- 三井化学
- 旭化成
- 東ソー
- DIC
- ダイセル
- カネカ
- 東洋紡
- 東レ
- 帝人
- ユニチカ
- 住友ベークライト
- JSR
- 日本ゼオン

### 対象開示

まずは以下だけでよい。

| 対象 | 理由 |
|---|---|
| 決算短信 | 四半期ごとの業績要因 |
| 決算説明資料 | セグメント・価格・数量・原料影響が最も出る |
| 業績予想修正 | 影響が強いイベントを拾える |
| 中期経営計画 | 設備投資・事業構造変化 |
| 設備投資・生産能力関連 | 供給能力変化 |
| 減損・撤退・構造改革 | 需要悪化・採算悪化の兆候 |

除外候補：

- 人事
- 定款変更
- コーポレートガバナンス報告書
- 自己株買い
- 配当予想のみ
- 株主総会関連
- 軽微なIRイベント

---

## 13. LLM抽出のステップ

パイプラインとしては以下。

1. **TDnetから対象企業の開示を取得**
2. **タイトルで一次分類**
   - 決算、修正、説明資料、設備投資、減損など
3. **対象外を除外**
4. **PDF本文抽出**
5. **マクロ関連箇所を検索**
   - 原材料、ナフサ、燃料、為替、中国、欧州、価格改定、在庫、関税、地政学など
6. **イベント単位に分割**
7. **テーマ分類を付与**
8. **事業・地域・財務影響を抽出**
9. **クラレ関連領域にマッピング**
10. **アラート/レポート候補を判定**

最初はタイトル分類だけではなく、本文中のキーワード検索を必ず入れた方がよい。  
タイトルには「決算短信」としか出ていなくても、本文中に一番欲しい情報が入っていることがあるため。

---

## 14. 最重要カラムを10個に絞るなら

MVPで絶対に外せないのは以下の10個。

| カラム | 理由 |
|---|---|
| `company_name` | どの同業か |
| `disclosure_date` | いつの情報か |
| `document_type` | 決算か修正か設備投資か |
| `macro_theme_l1` | 何のテーマか |
| `macro_theme_l2` | 具体的に何か |
| `kuraray_relevance_area` | クラレのどの事業に関係するか |
| `impact_mechanism` | どう効くか |
| `financial_metric` | どの財務項目に効くか |
| `impact_direction` | プラスかマイナスか |
| `evidence_text` | 根拠の原文 |

この10個があれば、週次アラートと四半期レポートの原材料になる。

---

## 結論

適時開示をデータソースにするなら、作るべき前段テーブルは、単なる開示一覧ではなく、

**同業他社の適時開示を、クラレ視点のマクロ影響イベントに変換したテーブル**

である。

最初のテーブル設計は、以下がよい。

**1行 = 1開示資料**ではなく、  
**1行 = 1社 × 1開示 × 1マクロテーマ × 1事業影響**

にする。

この粒度にしておくと、後から自然に以下へ展開できる。

- 週次アラート
- 四半期同業比較レポート
- テーマ別ダッシュボード
- クラレ事業別リスクマップ
- 経営会議向けインサイト
