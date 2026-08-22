# PPIH向け：小売マクロ・同業トレンドウォッチ設計メモ

## 1. 位置づけ

PPIH（パン・パシフィック・インターナショナルホールディングス）を対象顧客にする場合、クラレ向けの「素材・化学メーカーのマクロ感応度分析」とは設計思想が変わる。

クラレ向けでは、原燃料価格、ナフサ、天然ガス、為替、地域需要、設備投資などを、製品群別P/Lや原価構造に接続することが中心だった。

一方、PPIH向けでは、分析対象は小売業のため、マクロトレンドを以下に翻訳する必要がある。

- 既存店売上
- 客数
- 客単価
- 買上点数
- 商品カテゴリーミックス
- 粗利率
- 販管費率
- 人件費
- 賃料
- 物流費
- インバウンド需要
- 出店・改装・店舗効率

つまり、PPIH向けの本質は、同業他社の適時開示や月次情報から、

> 消費環境、価格競争、インバウンド、人件費、賃料、物流費などの変化が、PPIHの業態・商品カテゴリ・顧客層・既存店売上ドライバーにどう効くかを構造化すること

である。

プロダクトの位置づけとしては、以下に近い。

- 小売マクロ・同業トレンドウォッチ
- 消費・価格競争インテリジェンス
- 小売業向け外部環境モニタリング
- 競合同業開示からの経営インサイト抽出

---

## 2. PPIH向けに見るべき同業・周辺企業

PPIHは、ドン・キホーテ、アピタ、ピアゴ等を展開するため、対象同業は単純なGMSだけでは足りない。

ディスカウント、ドラッグストア、食品スーパー、家電量販、百貨店、観光消費関連まで広げる必要がある。

| グループ | 候補企業 | PPIHにとっての比較価値 |
|---|---|---|
| 総合小売・GMS | イオン、セブン＆アイ、イズミ、平和堂、フジ | 食品・日用品・衣料・テナント・地方消費 |
| ディスカウント/量販 | トライアルHD、コスモス薬品、MrMaxHD | 低価格業態、節約志向、価格競争 |
| ドラッグストア | ウエルシア、ツルハ、マツキヨココカラ、サンドラッグ、スギHD | 食品・日用品・化粧品・医薬品・インバウンド需要 |
| 家電/専門量販 | ビックカメラ、ヤマダHD、エディオン、ニトリHD | インバウンド、耐久消費財、為替、PB/輸入 |
| 食品スーパー | ライフ、ヤオコー、バローホールディングス、ベルク、アークス | 食品インフレ、客数、客単価、粗利 |
| コンビニ | ローソン、セブン＆アイ、ファミリーマート親会社経由 | 都市部需要、客数、単価、訪日客 |
| 免税・観光消費 | J.フロント、高島屋、三越伊勢丹、エイチ・ツー・オー | インバウンド消費、都市部/観光地需要 |

### 初期MVPの対象企業例

最初は広げすぎず、以下のような15〜20社程度に絞るのが現実的。

- イオン
- セブン＆アイ
- トライアルHD
- コスモス薬品
- ウエルシアHD
- ツルハHD
- マツキヨココカラ
- サンドラッグ
- スギHD
- ライフ
- ヤオコー
- バローホールディングス
- ベルク
- ビックカメラ
- ヤマダHD
- ニトリHD
- 三越伊勢丹HD
- J.フロント リテイリング
- 高島屋

---

## 3. PPIH向けマクロテーマ分類

クラレ向けの `input_cost / fx / regional_demand / price_pass_through` という分類は一部使えるが、PPIH向けには小売業に合わせて分類し直す必要がある。

| macro_theme_l1 | macro_theme_l2 | PPIHへの効き方 |
|---|---|---|
| `consumer_spending` | 実質賃金、消費者マインド、節約志向 | 客数、買上点数、PB比率、低価格業態への流入 |
| `inflation` | 食品CPI、日用品、電気代、生活必需品価格 | 客単価上昇、買上点数減、粗利率変化 |
| `price_competition` | 値下げ、EDLP、特売、PB強化 | 価格競争、粗利率、既存店売上 |
| `inbound` | 訪日客数、免税売上、国籍別消費 | 都市型ドンキ、化粧品、菓子、医薬品、家電雑貨 |
| `fx` | 円安、仕入為替、訪日消費 | 輸入原価上昇、インバウンド追い風 |
| `labor_cost` | 最低賃金、人件費、人手不足 | 販管費率、営業時間、店舗運営コスト |
| `rent_real_estate` | 賃料、出店コスト、不動産価格 | 店舗採算、出退店、既存店改装投資 |
| `supply_chain` | 物流費、燃料費、調達難 | 粗利、在庫、欠品、配送コスト |
| `category_demand` | 食品、日用品、化粧品、家電、衣料 | カテゴリーミックス、客単価、粗利率 |
| `regulation_tax` | 免税制度、酒税、薬機、インボイス等 | 商品構成、免税販売、オペレーション |

### PPIH向けの主要テーマ

PPIH向けで特に重要な外部環境は以下。

- 食品・日用品インフレ
- 実質賃金
- 消費者マインド
- 節約志向
- 低価格志向
- インバウンド需要
- 円安
- 輸入仕入コスト
- 人件費上昇
- 賃料上昇
- 物流費上昇
- 電気代・店舗運営コスト
- PB強化
- 価格競争
- 免税制度変更
- 出店余地
- 地方消費
- 都市部・観光地需要

---

## 4. PPIH向けテーブル設計の考え方

クラレ向けでは、以下の粒度が適していた。

> 1行 = 1社 × 1開示 × 1マクロテーマ × 1事業影響

PPIH向けでは、より小売ドライバーに寄せて、以下の粒度にする。

> 1行 = 1社 × 1開示 × 1小売マクロテーマ × 1業態/商品カテゴリ × 1売上・利益ドライバー

つまり、開示資料から抽出するのは、単なるニュースではなく、以下のようなイベントである。

- 食品インフレによって客単価が上昇した
- 節約志向によってディスカウント業態の客数が増加した
- 価格競争によって粗利率が低下した
- 免税売上の増加により都市型店舗に追い風がある
- 人件費上昇により販管費率が上がった
- 物流費上昇により配送コストが増加した
- PB強化によって粗利率が改善した
- 出店・改装により店舗効率が変化した

---

## 5. 追加すべきカラム

前回の汎用 `peer_macro_event_table` に加えて、PPIH向けには以下のカラムを追加したい。

| カラム | 例 | 理由 |
|---|---|---|
| `retail_format` | `discount_store`, `gms`, `drugstore`, `supermarket`, `department_store` | 業態別に比較するため |
| `sales_driver` | `traffic`, `basket_size`, `unit_price`, `purchase_frequency`, `store_count` | 売上分解に接続するため |
| `same_store_sales_impact` | `positive`, `negative`, `mixed` | 既存店売上への示唆 |
| `customer_segment` | `domestic_budget`, `inbound_tourist`, `family`, `senior`, `youth` | 顧客層別に効き方が違う |
| `product_category` | `food`, `daily_goods`, `cosmetics`, `pharma`, `electronics`, `apparel`, `luxury`, `fresh_food` | PPIHの商品カテゴリに接続 |
| `gross_margin_impact` | `increase`, `decrease`, `mixed` | 値上げ/値下げ/ミックス変化を見る |
| `sg_and_a_impact` | `labor`, `rent`, `utilities`, `logistics`, `advertising` | 販管費要因を分ける |
| `inbound_relevance` | `high`, `medium`, `low` | ドンキ業態では重要 |
| `store_operation_impact` | `opening`, `closing`, `renovation`, `labor_saving`, `hours_change` | 店舗戦略に接続 |

---

## 6. `peer_retail_macro_event_table` の設計

MVPでは、以下のワイドテーブルから始めるのが現実的。

| カラム | 型 | 例 |
|---|---|---|
| `event_id` | string | `evt_000001` |
| `disclosure_id` | string | `disc_20260510_7532_xxxx` |
| `disclosure_date` | date | `2026-05-10` |
| `ticker` | string | `7532` |
| `company_name` | string | `パン・パシフィック・インターナショナルホールディングス` |
| `peer_group` | string | `retail_discount` |
| `title` | string | `2026年6月期 第3四半期決算短信` |
| `document_type` | enum | `earnings_release`, `earnings_presentation`, `monthly_sales`, `forecast_revision`, `business_plan`, `capex`, `other` |
| `retail_format` | enum | `discount_store`, `gms`, `drugstore`, `supermarket`, `department_store`, `electronics_retail`, `convenience_store`, `other` |
| `macro_theme_l1` | enum | `consumer_spending`, `inflation`, `price_competition`, `inbound`, `fx`, `labor_cost`, `rent_real_estate`, `supply_chain`, `category_demand`, `regulation_tax` |
| `macro_theme_l2` | string | `saving_mindset`, `food_inflation`, `tax_free_sales`, `yen_depreciation`, `minimum_wage` |
| `event_direction` | enum | `positive`, `negative`, `mixed`, `neutral`, `unclear` |
| `impact_strength` | enum | `high`, `medium`, `low`, `unclear` |
| `time_horizon` | enum | `current_month`, `current_quarter`, `next_quarter`, `full_year`, `medium_term`, `unclear` |
| `sales_driver` | enum | `traffic`, `basket_size`, `unit_price`, `purchase_frequency`, `store_count`, `same_store_sales`, `category_mix` |
| `product_category` | enum | `food`, `daily_goods`, `cosmetics`, `pharma`, `electronics`, `apparel`, `luxury`, `fresh_food`, `household_goods`, `other` |
| `customer_segment` | enum | `domestic_budget`, `inbound_tourist`, `family`, `senior`, `youth`, `urban_worker`, `unknown` |
| `same_store_sales_impact` | enum | `positive`, `negative`, `mixed`, `unclear` |
| `gross_margin_impact` | enum | `increase`, `decrease`, `mixed`, `unclear` |
| `sg_and_a_impact` | enum | `labor`, `rent`, `utilities`, `logistics`, `advertising`, `mixed`, `none`, `unclear` |
| `inbound_relevance` | enum | `high`, `medium`, `low`, `none`, `unclear` |
| `store_operation_impact` | enum | `opening`, `closing`, `renovation`, `labor_saving`, `hours_change`, `none`, `unclear` |
| `ppih_relevance_area` | enum | `domestic_discount`, `gms_uny`, `inbound_tax_free`, `food_daily_goods`, `cosmetics_healthcare`, `electronics_lifestyle`, `private_brand`, `store_network`, `labor_operations`, `procurement_fx`, `unknown_or_indirect` |
| `financial_metric` | enum | `sales`, `same_store_sales`, `gross_margin`, `operating_profit`, `sg_and_a`, `inventory`, `cash_flow`, `capex` |
| `impact_direction` | enum | `increase`, `decrease`, `mixed`, `unclear` |
| `amount_value` | numeric | `null` |
| `amount_unit` | enum | `JPY_mn`, `JPY_bn`, `percent`, `bps`, `unknown` |
| `offsetting_factor` | string | `PB強化`, `価格改定`, `販促抑制` |
| `normalized_summary` | text | `食品・日用品価格上昇で客単価は上昇する一方、節約志向により買上点数や粗利率に圧力。` |
| `evidence_text` | text | 原文該当箇所 |
| `source_url` | string | PDF URL |
| `page_number` | int | `12` |
| `confidence` | float | `0.84` |
| `recommended_output` | enum | `weekly_alert`, `monthly_dashboard`, `quarterly_report`, `archive_only`, `exclude` |

---

## 7. PPIH視点の `ppih_relevance_area`

クラレ向けの `kuraray_relevance_area` に相当する正規化軸。

同業開示を読んだとき、PPIHのどこに関係するかを必ず付与する。

| ppih_relevance_area | 内容 |
|---|---|
| `domestic_discount` | ドン・キホーテ等の国内ディスカウント |
| `gms_uny` | アピタ・ピアゴ等のUNY/GMS |
| `inbound_tax_free` | 免税・訪日客需要 |
| `food_daily_goods` | 食品・日用品 |
| `cosmetics_healthcare` | 化粧品、医薬品、衛生用品 |
| `electronics_lifestyle` | 家電、雑貨、生活用品 |
| `private_brand` | PB、情熱価格、粗利改善 |
| `store_network` | 出店、改装、店舗効率 |
| `labor_operations` | 人件費、省人化、店舗運営 |
| `procurement_fx` | 輸入仕入、為替、物流 |
| `unknown_or_indirect` | 間接的・判定困難 |

この軸を入れると、以下のような分析が可能になる。

- 国内ディスカウント業態に関係する同業開示だけを見る
- インバウンド関連のイベントだけ集計する
- UNY/GMSに関係する食品スーパー・GMSの開示だけ比較する
- PB/情熱価格に関係する価格競争や粗利改善の事例を見る
- 店舗運営コストに関係する人件費・賃料・電気代の開示を横断する

---

## 8. レコード例

### 例1：ドラッグストア/ディスカウント系の食品・日用品インフレ

| カラム | 値の例 |
|---|---|
| `company_name` | コスモス薬品 |
| `disclosure_date` | `2026-xx-xx` |
| `document_type` | `earnings_presentation` |
| `retail_format` | `drugstore_discount` |
| `macro_theme_l1` | `inflation` |
| `macro_theme_l2` | `food_daily_goods_price` |
| `sales_driver` | `basket_size` |
| `product_category` | `food`, `daily_goods` |
| `customer_segment` | `domestic_budget` |
| `impact_mechanism` | `unit_price_up_purchase_volume_down` |
| `financial_metric` | `same_store_sales`, `gross_margin` |
| `impact_direction` | `mixed` |
| `ppih_relevance_area` | `domestic_discount`, `food_daily_goods` |
| `normalized_summary` | 食品・日用品価格上昇で客単価は上昇する一方、節約志向により買上点数や粗利率に圧力。 |
| `recommended_output` | `weekly_alert` |

### 例2：百貨店の免税売上増加

| カラム | 値の例 |
|---|---|
| `company_name` | 三越伊勢丹HD |
| `document_type` | `earnings_presentation` |
| `macro_theme_l1` | `inbound` |
| `macro_theme_l2` | `tax_free_sales` |
| `retail_format` | `department_store` |
| `customer_segment` | `inbound_tourist` |
| `product_category` | `cosmetics`, `luxury`, `fashion` |
| `sales_driver` | `traffic`, `basket_size` |
| `impact_mechanism` | `inbound_spending_up` |
| `ppih_relevance_area` | `inbound_tax_free`, `cosmetics_healthcare` |
| `normalized_summary` | 免税売上の増加は、都市型店舗・観光地店舗における訪日客需要の追い風を示唆。 |
| `recommended_output` | `monthly_dashboard` |

### 例3：食品スーパーの人件費・物流費上昇

| カラム | 値の例 |
|---|---|
| `company_name` | ライフコーポレーション |
| `document_type` | `earnings_release` |
| `macro_theme_l1` | `labor_cost` |
| `macro_theme_l2` | `wage_increase` |
| `retail_format` | `supermarket` |
| `product_category` | `food`, `fresh_food` |
| `sales_driver` | `same_store_sales` |
| `financial_metric` | `sg_and_a`, `operating_profit` |
| `impact_direction` | `decrease` |
| `sg_and_a_impact` | `labor`, `logistics` |
| `ppih_relevance_area` | `gms_uny`, `labor_operations` |
| `normalized_summary` | 人件費・物流費の上昇が販管費を押し上げ、食品スーパー/GMS型業態の利益率に圧力。 |
| `recommended_output` | `weekly_alert` |

---

## 9. PPIH向けに作るべき集計ビュー

### 9.1 小売マクロテーマ別イベント集計

| theme | 直近週 | 直近月 | 主な企業 | PPIHへの示唆 |
|---|---:|---:|---|---|
| 食品・日用品インフレ | 6件 | 22件 | 食品スーパー、ドラッグ | 客単価上昇、買上点数減、価格競争 |
| 節約志向 | 4件 | 15件 | ディスカウント、GMS | 低価格業態に追い風。ただし粗利圧力 |
| インバウンド | 3件 | 10件 | 百貨店、家電量販 | 都市型ドンキ、免税売上に追い風 |
| 人件費上昇 | 5件 | 18件 | スーパー、ドラッグ | 販管費率上昇、省人化投資 |
| 物流費上昇 | 2件 | 8件 | 小売全般 | 原価・配送コスト増、在庫政策変更 |

### 9.2 PPIH業態別リスク/追い風ビュー

| ppih_area | 関連イベント | 主なテーマ | 方向感 |
|---|---:|---|---|
| 国内ディスカウント | 18 | 節約志向、食品インフレ、価格競争 | mixed/positive |
| UNY/GMS | 12 | 食品インフレ、人件費、地方消費 | mixed/negative |
| インバウンド免税 | 9 | 訪日客、円安、化粧品需要 | positive |
| PB/情熱価格 | 7 | 価格競争、粗利改善、仕入為替 | mixed |
| 店舗運営 | 10 | 人件費、賃料、電気代、省人化 | negative |

### 9.3 売上ドライバー別ビュー

| sales_driver | 同業での言及 | PPIHへの意味 |
|---|---|---|
| `traffic` | 客数回復、訪日客増、節約来店 | 既存店客数の先行材料 |
| `basket_size` | 値上げによる客単価上昇 | 売上増だが数量減リスク |
| `purchase_frequency` | 節約志向で買い回り増/減 | ディスカウント優位性 |
| `store_count` | 出店加速/抑制 | PPIHの出店余地比較 |
| `gross_margin` | PB強化、値下げ、原価上昇 | 利益率への示唆 |

### 9.4 アラート候補リスト

| priority | company | why_alert | ppih_area | action |
|---:|---|---|---|---|
| 1 | コスモス薬品 | 食品・日用品の低価格競争が強まっている | `domestic_discount`, `food_daily_goods` | 価格競争テーマに追加 |
| 2 | 三越伊勢丹HD | 免税売上が大きく伸長 | `inbound_tax_free` | 都市型店舗需要の追い風として確認 |
| 3 | ライフ | 人件費・物流費上昇で販管費圧迫 | `gms_uny`, `labor_operations` | UNY業態のコスト比較に反映 |
| 4 | ビックカメラ | 訪日客の家電・化粧品需要に言及 | `inbound_tax_free` | 商品カテゴリ別需要に反映 |

---

## 10. クラレ向けとの違い

| 観点 | クラレ | PPIH |
|---|---|---|
| 分析単位 | 製品群・拠点・原料 | 業態・店舗・商品カテゴリ・顧客層 |
| 主要マクロ | ナフサ、ガス、為替、地域需要 | 消費、物価、賃金、インバウンド、為替、人件費 |
| 財務接続 | 原価、数量、価格、在庫、ROIC | 既存店売上、客数、客単価、粗利率、販管費率 |
| 同業開示の価値 | 需給・価格転嫁・設備投資 | 消費トレンド・価格競争・カテゴリーミックス |
| アラート対象 | 原燃料高、設備増強、需要減速 | 節約志向、免税売上、食品インフレ、人件費、出店 |

クラレ向けは、製品群ごとの原価・価格・数量・在庫・設備投資を追う。

PPIH向けは、業態別・カテゴリ別・顧客層別に、客数、客単価、粗利、販管費、店舗効率を追う。

---

## 11. データソース設計

当初の方針としては、まず適時開示を主データソースにする。

ただし、PPIH向けでは、適時開示だけだとやや弱い可能性がある。

理由は、小売業では月次売上高の情報価値が非常に高いためである。

したがって、MVPでは以下の優先順位がよい。

| 優先度 | データソース | 目的 |
|---:|---|---|
| 1 | 適時開示 | 決算短信、決算説明資料、業績予想修正、出店/閉店、事業戦略 |
| 2 | 月次売上高 | 既存店売上、客数、客単価、免税売上、店舗数 |
| 3 | 決算説明資料 | カテゴリー別、業態別、販管費、粗利要因の詳細 |
| 4 | 有価証券報告書 | 年次の事業構造、リスク、地域・セグメント情報 |
| 5 | 統合報告書・中計 | 中期的な出店戦略、PB戦略、インバウンド戦略 |

初期は「適時開示のみ」でよいが、PPIH向けの価値を高めるには、同業の月次売上情報を準適時開示として取り込むことが望ましい。

---

## 12. 抽出パイプライン

PPIH向けの抽出パイプラインは以下。

1. 対象企業の適時開示を取得
2. タイトルで一次分類
   - 決算短信
   - 決算説明資料
   - 月次売上
   - 業績予想修正
   - 出店/閉店
   - 中期経営計画
   - その他
3. 対象外の開示を除外
   - 人事
   - 定款変更
   - 株主総会
   - コーポレートガバナンス
   - 配当のみ
   - 自己株買いのみ
4. PDF本文抽出
5. 小売マクロ関連箇所を検索
   - 既存店
   - 客数
   - 客単価
   - 食品
   - 日用品
   - 価格改定
   - 値下げ
   - PB
   - インバウンド
   - 免税
   - 人件費
   - 物流費
   - 電気代
   - 賃料
   - 出店
   - 改装
   - 在庫
6. イベント単位に分割
7. `macro_theme_l1/l2` を付与
8. 業態、商品カテゴリ、顧客層を抽出
9. 売上・利益ドライバーにマッピング
10. `ppih_relevance_area` にマッピング
11. アラート/レポート候補を判定

---

## 13. 最重要カラム10個

MVPで絶対に外せないのは以下。

| カラム | 理由 |
|---|---|
| `company_name` | どの同業か |
| `disclosure_date` | いつの情報か |
| `document_type` | 決算か月次か修正か |
| `retail_format` | 業態比較に必要 |
| `macro_theme_l1` | 何のテーマか |
| `macro_theme_l2` | 具体的に何か |
| `ppih_relevance_area` | PPIHのどこに関係するか |
| `sales_driver` | 売上分解に接続するため |
| `impact_direction` | プラスかマイナスか |
| `evidence_text` | 根拠の原文 |

この10個があれば、最低限の週次アラート、月次ダッシュボード、四半期レポートの材料になる。

---

## 14. 最初のMVPアウトプット

PPIH向けMVPでは、以下のアウトプットが考えられる。

### 14.1 週次アラート

- 同業の価格競争が強まっている
- 免税売上が急伸している
- 食品スーパーで人件費・物流費圧力が出ている
- ドラッグストアで食品・日用品の客数が増えている
- 百貨店・家電量販でインバウンド需要が増えている

### 14.2 月次ダッシュボード

- 同業の既存店売上トレンド
- 客数・客単価の方向感
- 食品・日用品・化粧品・家電などの商品カテゴリ別変化
- インバウンド関連イベント
- 人件費・物流費・賃料・電気代のコスト圧力

### 14.3 四半期同業比較レポート

- 小売各社の売上成長要因
- 客数と客単価の分解
- 粗利率の変化要因
- 価格競争とPB戦略
- インバウンド需要の業態別波及
- 販管費上昇と省人化投資
- PPIHへの示唆

---

## 15. 結論

PPIH向けの場合、作るべきテーブルは、クラレ向けの「同業マクロ影響イベントDB」を小売業向けに再設計したものである。

設計上の中心は、以下。

> 1行 = 1社 × 1開示 × 1小売マクロテーマ × 1業態/商品カテゴリ × 1売上・利益ドライバー

クラレ向けでは、同業開示を製品群別P/Lと原価・価格・数量に翻訳した。

PPIH向けでは、同業開示を以下に翻訳する。

- 業態
- 商品カテゴリ
- 顧客層
- 既存店売上
- 客数
- 客単価
- 粗利率
- 販管費率
- インバウンド
- 店舗運営

PPIH向けの主要テーマは、以下である。

- 消費環境
- 食品・日用品インフレ
- 節約志向
- 価格競争
- インバウンド
- 円安
- 輸入仕入コスト
- 人件費
- 賃料
- 物流費
- PB戦略
- 店舗効率

最初のMVPは、適時開示を主データソースにして、週次アラートと月次ダッシュボードの前段階となるイベントテーブルを作る。

ただし、PPIH向けでは月次売上高の価値が非常に高いため、次段階では同業の月次売上情報も取り込むべきである。
