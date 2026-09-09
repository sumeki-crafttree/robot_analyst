# 適時開示インテリジェンス・データパイプライン要件定義書

**版**: v0.2（2026年8月31日 / MVP）
**上位文書**: [ミッション・ビジョン](01_mission_vision.md) / [要求定義](02_requirement_business.md) / [要件定義（概要）](03_requirement_system_overview.md)
**位置づけ**: 03で定義した層とスキーマを、実装可能な粒度まで具体化する。03と矛盾する記述があれば03が優先する。

---

## 目次

1. [目的とv0.1からの変更](#1-目的とv01からの変更)
2. [03の層モデルへの対応](#2-03の層モデルへの対応)
3. [対象ソース](#3-対象ソース)
4. [分類体系](#4-分類体系)
5. [データモデル](#5-データモデル)
6. [LLM処理とルールの責務分離](#6-llm処理とルールの責務分離)
7. [品質管理](#7-品質管理)
8. [パイプライン](#8-パイプライン)
9. [具体例：ニッスイの価格改定開示](#9-具体例ニッスイの価格改定開示)
10. [論点の確定と後送り](#10-論点の確定と後送り)

---

## 1. 目的とv0.1からの変更

適時開示を取得し、文書検索ではなく**分析可能な構造化ファクト**へ変換する。基本思想はv0.1から変えない。

v0.1は分類コードが122個、LLM呼び出しが1開示あたり8回、未決論点が15個あり、1週間・月1万円の制約に収まらなかった。v0.2では以下を変更する。

| 項目 | v0.1 | v0.2 | 理由 |
|---|---|---|---|
| 分類コード総数 | 122 | **22** | 対象1社・週数十件の規模でコードあたりのデータが薄すぎる |
| LLM呼び出し | 1開示8回 | **1開示1回** | コスト上限 月1万円に収めるため |
| テーブル数 | 17前後 | **6** | 03のスキーマ定義に合わせる |
| confidence | 4種 | **2種** | 事実と推論の分離だけ残す |
| Human Review | 要件に含む | **スコープ外** | 01原則3「人が介在しないと出せない機能は入れない」と矛盾するため |
| 未決論点 | 15 | **0（3件を確定、12件を後送り）** | 論点を残したまま実装に入れないため |

v0.1の以下の判断は正しいため維持する。

- 生文書を必ず保存する。
- evidence spanを必ず保持する。
- 顧客非依存のファクトを先に作り、顧客固有の示唆を別レイヤーで付与する。
- LLMに最終DBレコードを直接生成させず、schema validationとmaster lookupを通す。
- 事実抽出のconfidenceと推論のconfidenceを混ぜない。

---

## 2. 03の層モデルへの対応

03が定義する6層に、本書の処理を対応させる。**v0.1の4レイヤー（Extraction / Normalization / Semantic Enrichment / Customer-specific Enrichment）は、03との対応が取れないため廃止する。**

| 03の層 | 本書の処理 | 実体 |
|---|---|---|
| data source | TDnetからの取得 | TDnet |
| original | 取得したPDF・XMLをそのまま保存 | GCS |
| raw | PDFのテキスト化、XMLのパース | GCS / BigQuery |
| processed | LLMによるファクト抽出・分類・示唆付与、schema validation | BigQuery |
| product | 6テーブルへの確定書き込み、参照用View | BigQuery |
| report | 週次レポート生成 | GCS / Cloudflare Pages |

- 意味を足す処理はすべてprocessed層に置く。raw層は機械可読化のみを行う。
- product層はprocessed層から決定的に生成し、LLMを呼ばない。

---

## 3. 対象ソース

適時開示のみを扱う（02§5）。TDnet上の区分に応じて `source_type` を保持する。

| `source_type` | 内容 | 主な用途 | MVPで処理 |
|---|---|---|---|
| `timely_disclosure` | 期中の個別開示 | イベント検知。価格改定・設備投資・M&A・事故など | ○ |
| `forecast_revision` | 業績予想修正 | 転換点検知 | ○ |
| `earnings` | 決算短信 | 定点観測。業績変動要因 | × Phase 2 |
| `earnings_presentation` | 決算説明資料 | 対応方針・見通し・セグメント別変化 | × Phase 2 |

**2系統の役割の違い**

- **期中開示は Event Stream である。** 「誰が・何を・いつ・どれくらいやるか」が明確で、イベント検知・転換点検知・企業アクションの構造化に向く。
- **四半期資料は State / Context Snapshot である。** マクロ環境・業績影響・経営対応がまとまっており、因果分解と対応方針の把握に向く。一方で経営者の総括や後付け説明が多く、イベントの発生時点が曖昧になりやすい。
- 両者は補完関係にある。期中開示が「9月から値上げ」を捉え、次の四半期資料が「原材料高で採算悪化、価格転嫁を進めた」という背景を与え、その次の四半期資料が「価格改定効果で利益率改善」という結果を与える。
- **MVP（Phase 1）は期中開示のみでイベントDBを作る。** 四半期資料はPhase 2で追加し、イベントの背景と結果を補完する。
- 判断根拠は3点ある。第一に、期中開示のほうが抽出対象が明確で、6.2の出力スキーマにそのまま乗る。第二に、企業横断で同一テーブルに並べて比較しやすい。第三に、四半期資料を要約するだけなら汎用LLMでも相当できるのに対し、期中開示を継続監視して時系列蓄積するほうがプロダクト固有のデータ資産になる。

**取得と処理の分離**

- **四半期資料もoriginal層には最初から取り込む。処理を行わないだけである。**
- 03§1の「original以外の全層はoriginalから再生成できる」という原則により、取得しておけばPhase 2で過去に遡って処理できる。取得しなければ過去分は永久に失われる。TDnetは過去開示の取得可能期間に制限があるため、これは後から戻せない差になる。
- 期中開示と決算資料は同一テーブルへ格納し、`source_type` で区別する。
- v0.1にあった `capex_announcement` / `restructuring` / `incident` は、開示の**種別**ではなく**内容**であるため `source_type` から外し、後述の `company_action` で表現する。

---

## 4. 分類体系

**コード総数は115。** 内訳は macro_theme L1 16（うち `other` 1）＋L2 85、company_action 8、action_status 3、relationship_type 3。L2はすべてL1配下の階層であり、次元数は増えていない。

### 4.1 `macro_theme`（15＋その他）

外部環境で何が起きたかを表す。**2階層とする。** 正本は `data/master/dim_macro_theme_seed.csv`（101行）であり、本節は一覧のみを示す。L1とL2は**同一ファイルに `level` 列で保持する**。ファイルを分けるとL1の定義とL2の対応が別管理になり、改定時にずれる。

| コード | 名称 |
|---|---|
| `commodity_price` | 商品市況・資源価格 |
| `import_price` | 輸入物価 |
| `fx` | 為替 |
| `labor_market` | 労働市場 |
| `demand` | 需要環境 |
| `consumer` | 消費・家計 |
| `financial_conditions` | 金融環境 |
| `trade_policy` | 通商政策 |
| `geopolitics` | 地政学 |
| `supply_chain` | サプライチェーン |
| `industry_supply_demand` | 業界需給 |
| `tech_investment_cycle` | 技術・投資サイクル |
| `regulation` | 規制・制度 |
| `asset_price` | 資産価格 |
| `weather_disaster` | 天候・自然災害 |
| `other` | その他（分類体系の欠落を検知する受け皿） |

**L2（サブテーマ）を持つ理由**

- **L1だけでは個社への翻訳ができない。** `commodity_price` と分かっても、原油なら物流費・包装資材へ、穀物なら飼料経由で畜産原料へ、水産物なら直接原価へと、波及経路が全く異なる。マクロ変数の粒度が、そのまま翻訳の精度になる。
- **横断比較にはコード化が必要である。** サブテーマを定義文の中の自由記述に留めると「原油に言及した開示を全社横断で」というクエリが書けない。
- 1次元内の階層であり、次元を増やすものではない。v0.2で削減した122コードは7次元の掛け算であって、性質が異なる。

**L2は任意項目とする**

- **L1は必須、L2は null を許容する。** 本文から確信を持ってL2を特定できない場合、LLMはL2を空で返す。
- これにより、L2が薄くてもL1での集計は常に成立する。データが分散して使えなくなる事態を避けるための設計である。
- L2の網羅性は運用で改善する。特定のL1に対してL2 nullが多いテーマは、L2の定義不足を示す信号として扱う。

**マスタが保持する項目**

| カラム | 用途 |
|---|---|
| `level` | `L1` / `L2` の別 |
| `theme_code` / `subtheme_code` | 識別子。L1行では `subtheme_code` は空 |
| `name` | 名称 |
| `definition` | 1文の定義 |
| `includes` | 含む例。判定の下限を示す |
| `excludes` | **含まない例。他テーマや他レイヤーとの境界を明示する** |
| `typical_expressions` | 開示本文での典型表現 |

**L2行は `definition` / `includes` / `excludes` を持たない**（空とする）。これらはL1に属する属性であり、L2行に複写すると改定時の不整合を招く。L2行が持つのは `name` と `typical_expressions` である。

- **`excludes` を必須項目とする。** 判定が揺れるのは境界例であり、「何を含むか」より「何を含まないか」のほうが一貫性に効く。たとえば `commodity_price`（国際市況）と `import_price`（日本への伝達段階）、`geopolitics`（情勢）と `trade_policy`（政策手段）、`financial_conditions`（金利）と `asset_price`（資産価格）は、いずれも `excludes` で相互に切り分けている。
- 1ファクトに複数付与できる。**上限は3件**とする。
- **レイヤーを越えたものは付与しない。** マクロテーマは「企業の外部で何が起きたか」であり、企業への影響（原材料コスト上昇）や企業アクション（値上げ）は含めない。各テーマの `excludes` にこの境界を明記している。
- マクロ要因の記述がない開示には、**テーマを付与しない**。`other` は「記述はあるが既存テーマで表現できない」場合に限る。

**採用の経緯**

- 日本銀行「経済・物価情勢の展望」2022年以降のBOX分析をトップダウンの参照源とし、網羅性を検証した上で構成している。詳細は[マクロテーマ分類体系](../99_feedback/2026-09-01_macro_theme_taxonomy.md)を参照。
- **`中国需要` `自動車需要` のような個別テーマは作らない。** `demand` × 地域 × 最終需要市場の組み合わせで表現する。テーマの増殖を避けるためである。
- 元案にあった「物価・価格形成」は採用していない。価格転嫁は外部で起きた事象ではなく**マクロ要因が企業に届く経路**であり、本次元の定義（外部で何が起きたか）に合わない。これを残すと1つの開示から `commodity_price`（原因）・価格形成（経路）・`price_change`（アクション）が同時に付与され、判定が揺れる。**必要になればマスタへの1行追加で戻せる。**

### 4.2 `company_action`（8）

企業が取った、または取ろうとしている対応。

| コード | 内容 |
|---|---|
| `price_change` | 価格改定 |
| `capex` | 設備投資 |
| `capacity_change` | 生産能力の増減 |
| `facility_change` | 拠点の開設・閉鎖 |
| `product_launch` | 新製品・新サービス投入 |
| `m_and_a` | 買収・売却・資本提携 |
| `forecast_revision` | 業績予想の修正 |
| `cost_reduction` | コスト削減施策 |

- 方向は `direction` カラム（`up` / `down` / `neutral`）で表現する。`price_increase` と `price_decrease` をコードで分けない。
- **v0.1の `dim_impact_mechanism`（31コード）は廃止する。** 廃止理由は2つある。第一に、`raw_material_cost_up` は `macro_theme = input_cost` とほぼ1対1であり、情報が重複する。第二に、`inventory_build` `capacity_expansion` `capex_increase` `capex_delay` がv0.1の `dim_company_action` と**同じコードで重複しており**、LLMがどちらへ入れるべきか判断できない。

### 4.3 `action_status`（3）

`planned` / `announced` / `completed`

- v0.1の `considering` は `planned` に、`in_progress` は `announced` に含める。`cancelled` は出現頻度が低いためMVPでは扱わない。

### 4.4 `relationship_type`（3）

**ウォッチ企業から見た**関連企業の関係区分。**02§2および03§3の定義に従う。**

`peer` / `partner` / `customer`

- 1つの（ウォッチ企業, 関連企業）の組に対して複数付与できる。
- v0.1の13区分（`peer_direct` 〜 `macro_proxy`）は、02が定義する3区分と整合しないため採用しない。
- **関係は企業の属性ではなく、ウォッチ企業と関連企業の間の辺である。** 同じ企業でも、どのウォッチ企業から見るかで関係が変わるため（味の素はニチレイから見れば `peer` かつ `partner`、キオクシアから見れば無関係）、`dim_company` の属性にはできない。`bridge_watch_company` に保持する（5章）。

### 4.5 廃止する分類軸

| 軸 | v0.1のコード数 | 廃止理由 |
|---|---|---|
| `dim_impact_mechanism` | 31 | macro_themeと重複し、company_actionともコードが衝突する |
| `dim_end_market` | 22 | 対象が食品業界のみのため、大半が同一値になる |
| `dim_region` | 13 | 国内適時開示が対象のため、ほぼ `japan` に固定される |

- これらは業種を横展開する段階で再検討する。MVPでは列そのものを作らない。

---

## 5. データモデル

**03§4が定義する6テーブルを正とする。** v0.1の `fact_event` + `bridge_event_*` 構成は採用しない。

### 5.1 テーブル

| テーブル | 種別 | 内容 |
|---|---|---|
| `dim_company` | マスタ | 企業マスタ。証券コード・名称・業種のみ。関係は持たない |
| `bridge_watch_company` | ブリッジ | ウォッチ企業 × 関連企業。関係区分・優先度・接点事業領域 |
| `dim_macro_theme` | マスタ | マクロテーマ8件の定義 |
| `fact_disclosure` | ファクト | 開示の原本メタデータ。マスタ突合結果を含む |
| `fact_extracted_fact` | ファクト | 開示から抽出したファクト |
| `fact_theme_mapping` | ブリッジ | ファクト × マクロテーマ |
| `fact_implication` | ファクト | ファクト × ウォッチ企業への示唆 |

### 5.2 主なカラム

**`dim_company`**（純粋な企業マスタ）

```text
company_id          証券コード
company_name        JPXマスタ上の名称
jpx_sector_17       17業種区分
jpx_sector_33       33業種区分
```

**`bridge_watch_company`**（ウォッチ企業から見た関係）

```text
watch_company_id    ウォッチ企業の証券コード
company_id          関連企業の証券コード
relationship_type   peer / partner / customer（複数可）
priority            high / mid / low
business_area       ウォッチ企業と接する事業領域
note                選定理由
```

- ウォッチ企業の集合は `bridge_watch_company.watch_company_id` の distinct として定義される。`is_target` フラグは持たない。
- `watch_company_id = company_id` の行は作らない。自社に対する関係区分は定義しないため。

**`fact_disclosure`**

```text
disclosure_id
company_id
disclosure_datetime
title
source_type
original_uri        GCS上の原本パス
is_relevant         マスタ突合の結果
```

**`fact_extracted_fact`**

```text
fact_id
disclosure_id
company_id
fact_date           事象の発生・公表日
effective_date      効力発生日（あれば）
summary             1文
company_action      4.2のコード
action_status       4.3のコード
direction           up / down / neutral
quantitative_value  数値（あれば）
quantitative_unit   pct / jpy / count
evidence_text       根拠となる原文
evidence_offset     原文中の位置
extraction_confidence
taxonomy_version
```

**`fact_theme_mapping`**

```text
fact_id
macro_theme_id
```

**`fact_implication`**

```text
fact_id
target_company_id
implication         自社にとっての意味（自然言語1文）
expected_direction  positive / negative / neutral
inference_confidence
```

### 5.3 参照用View

- product層に**非正規化Viewを1本だけ**置く。名称は `v_fact_enriched` とする。
- 6テーブルをJOINし、1ファクト1行で読める形にする。
- 判断根拠は、要求定義§3の「開発者が毎日使って嬉しいデータ基盤」である。6本のJOINを毎回書く必要があるデータは、日常的に引かれない。
- Viewであるため保存コストは発生しない。v0.1が提案していた用途別mart 4本は、MVPでは作らない。

---

## 6. LLM処理とルールの責務分離

### 6.1 1開示1コール

- **1件の開示につき、LLM呼び出しは1回とする。**
- 1回のstructured outputで、ファクト・マクロテーマ・企業アクション・示唆をまとめて取得する。
- 判断根拠はコスト制約である。v0.1の17ステップ構成ではLLM呼び出しが1開示あたり8回発生し、03§7の想定（月3,000〜6,000円）を大きく超える。
- 精度が不足する工程が判明した時点で、その工程のみ分離する。最初から分割すると、コストが8倍のまま精度検証に入ることになる。

### 6.2 出力スキーマ

```json
{
  "facts": [
    {
      "summary": "string",
      "fact_date": "YYYY-MM-DD",
      "effective_date": "YYYY-MM-DD | null",
      "macro_themes": ["commodity_price"],
      "macro_subthemes": ["grain"],
      "company_action": "price_change",
      "action_status": "announced",
      "direction": "up",
      "quantitative_value": 17.0,
      "quantitative_unit": "pct",
      "evidence_text": "string",
      "extraction_confidence": 0.0,
      "implication": "string",
      "expected_direction": "positive",
      "inference_confidence": 0.0
    }
  ]
}
```

- `macro_themes`（L1）は最大3件。`macro_subthemes`（L2）は任意で、特定できない場合は空配列とする。
- コード値は4章の定義以外を許容しない。違反時はvalidationで弾く。

### 6.3 粒度

- **1開示から複数ファクトを許容する。** ただし1開示1イベントを基本とし、価格改定の商品カテゴリー別のように明確に分かれる場合のみ複数行にする。
- v0.1の `event_cluster_id`（同一事象の複数ソース横断）はMVPでは扱わない。

---

### 6.4 LLMとルールの責務分離

v0.1の方針を維持する。**LLMに最終DBレコードを直接生成させない。**

| LLMが担う | ルール・コードが担う |
|---|---|
| 文書の意味理解 | 証券コード・企業ID解決 |
| ファクトの切り出し | 日付の正規化 |
| マクロテーマへの分類 | 数値・単位の正規化 |
| 企業アクションの識別 | taxonomyコードの検証 |
| evidence spanの特定 | schema validation |
| ウォッチ企業への示唆の推論 | 重複排除・冪等性の担保 |
| | 原本URIの管理 |

- LLMは候補値と根拠を返し、後段でvalidationとmaster lookupを行う。
- validationを通過しなかった値は採用せず、7.2の扱いに従う。

---

## 7. 品質管理

### 7.1 Confidence設計

**2種類のみ保持する。**

| 名称 | 意味 | 例 |
|---|---|---|
| `extraction_confidence` | 原文からその事実を正しく抽出できている確度 | 「9月1日から値上げ」→ 0.99 |
| `inference_confidence` | ウォッチ企業への示唆を推論した確度 | 競合値上げ → 自社の価格転嫁余地拡大 → 0.73 |

- **事実抽出のconfidenceと推論のconfidenceを混ぜないことを必須とする。** これはv0.1の判断を維持する。
- v0.1の `normalization_confidence` と `relevance_confidence` は、それぞれ `extraction_confidence` と `inference_confidence` に含める。分類の誤りは抽出の誤りとして扱い、関連性の判定は推論として扱う。
- 低confidenceのレコードはフラグを立てるのみとし、**レビューキューは作らない**（7.2）。

---

### 7.2 失敗時の扱い

- schema validationに失敗した場合、同一開示に対して**1回だけリトライ**する。
- 再度失敗した場合は `status = failed` として記録し、パイプライン全体は継続する。
- 失敗件数は日次のログに残し、閾値を超えた場合のみメールで通知する。
- **Human Reviewの仕組みはMVPでは作らない。** 判断根拠は、01原則3「人が介在しないと出せない機能は、MVPのスコープに入れない」および02§8の成功基準「人手を介さず自動生成された実績が2週連続」と矛盾するためである。
- 低confidenceのレコードは `v_fact_enriched` から確認できる状態にし、人が見たい時に見られるようにする。それ以上の仕組みは持たない。

---

## 8. パイプライン

v0.1の17ステップを**9ステップに集約する**。

**日次ジョブ**

1. TDnetから当日分の開示を取得し、**source_typeを問わず**original層へ保存する
2. `bridge_watch_company` の `company_id` と証券コードで突合し、いずれのウォッチ企業とも関係のない開示を除外する
3. `source_type` で絞り込み、MVPの処理対象（`timely_disclosure` / `forecast_revision`）以外を以降の処理から外す
4. PDF・XMLをテキスト化し、raw層へ保存する
5. LLMを1開示1回呼び、structured outputを得る
6. schema validation、コード検証、数値・日付の正規化を行う
7. 6テーブルへ書き込む

**週次ジョブ**

8. product層から当週分を集約し、アナリストレポートを生成する
9. GCSへ版として保存し、Cloudflare Pagesへ配信、完了をメール通知する

- **ステップ2と3をLLM呼び出しより前に置く。** 対象外企業の開示にLLMを呼ばず、四半期資料の長文にもLLMを呼ばない。これがコスト削減に最も効く。
- ステップ1だけは絞り込みの対象外とし、全開示をoriginal層へ落とす。Phase 2で四半期資料を遡って処理できるようにするためである。
- 各ステップは冪等とし、同一日の再実行が重複を生まないこと。

---

## 9. 具体例：ニッスイの価格改定開示

### 9.1 入力

```json
{
  "company_name": "ニッスイ",
  "ticker": "1332",
  "disclosure_date": "2026-06-01",
  "title": "家庭用冷凍食品・家庭用加工食品・業務用冷凍食品の一部商品の出荷価格改定",
  "body_text": "原材料の価格高騰、国内外での人件費の増加、燃料・包装資材費および物流費の上昇が続いています。..."
}
```

### 9.2 出力（v0.2のモデル）

```json
{
  "fact_id": "fct_20260601_1332_001",
  "disclosure_id": "20260601_1332_001",
  "company_id": "1332",
  "fact_date": "2026-06-01",
  "effective_date": "2026-09-01",
  "summary": "家庭用・業務用の冷凍食品および加工食品について、2〜30%の出荷価格改定を発表",
  "macro_themes": ["input_cost", "labor", "logistics"],
  "company_action": "price_change",
  "action_status": "announced",
  "direction": "up",
  "quantitative_value": 30.0,
  "quantitative_unit": "pct",
  "evidence_text": "原材料の価格高騰、国内外での人件費の増加、燃料・包装資材費および物流費の上昇が続いています。",
  "extraction_confidence": 0.98,
  "implication": "競合が2〜30%の価格改定に踏み切っており、冷凍食品業界で価格転嫁が進行している。ニチレイの価格政策にも転嫁余地が広がっている可能性がある。",
  "expected_direction": "positive",
  "inference_confidence": 0.73
}
```

### 9.3 v0.1との差分

- 燃料費・包装資材費は、v0.1では `energy_cost_up` `packaging_cost_up` として個別コードを持っていたが、v0.2では `input_cost` に集約する。原文は `evidence_text` に保持されるため、情報は失われない。
- 商品カテゴリー別の価格改定率（家庭用冷凍食品 +2〜17%、業務用冷凍食品 +2〜30%）は、MVPでは最大値のみを `quantitative_value` に保持する。カテゴリー別に分けたい場合は6.3に従い複数ファクトとする。
- `end_market`（`food_retail` / `foodservice`）と `region`（`japan`）は保持しない。
- v0.1はニッスイに `peer_direct` と `supplier_signal` の両方を付与していたが、**v0.2では `peer` のみとする**。ニッスイはニチレイの仕入先ではなく、`supplier_signal` は定義が曖昧であるため採用しない。

---

## 10. 論点の確定と後送り

### 10.1 MVPで確定した論点

v0.1§16の15論点のうち、実装に着手するために必要な3件を確定する。

| 論点 | 確定内容 |
|---|---|
| 1開示を何ファクトに分割するか | 1開示1ファクトを基本とし、明確に分かれる場合のみ複数（6.3） |
| macro_themeの複数付与 | 許可する。上限3件（4.1） |
| `impact_path` の形式 | 構造化せず、自然言語1文の `implication` として保持（5.2） |

---

### 10.2 MVP後へ送る論点

以下はMVPでは扱わない。実装に着手する前に決める必要がないため、稼働後の実データを見てから判断する。

- `impact_mechanism` の再導入要否
- `end_market` / `region` の再導入要否（業種横展開時に再検討）
- 同一事象の複数ソース横断（`event_cluster_id`）
- taxonomyのバージョニングと、変更時の過去データ再分類
  - MVPでは `fact_extracted_fact.taxonomy_version` に版を記録するのみとし、再分類は行わない
- Human Reviewとcorrectionの蓄積
- 用途別martの追加
- 顧客固有relevanceのスコアリング方式（ルール／LLM／学習モデル）
- API提供
