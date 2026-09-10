# 詳細設計：マクロテーマ付与パイプライン

**版**: v0.1（2026年9月7日）
**上位文書**: [要件定義（概要）](../00_requirement/03_requirement_system_overview.md) / [パイプライン要件定義書](../00_requirement/04_requirement_system_detail.md) / [プロダクト設計書](../00_requirement/05_product_design.md)
**位置づけ**: 上位文書が定めた設計に準拠しつつ、**マクロテーマ付与のみ**に絞った実装単位の詳細設計。上位文書と矛盾する場合は上位が優先する。

---

## 目次

1. [スコープ](#1-スコープ)
2. [全体フローと既存コードの再利用](#2-全体フローと既存コードの再利用)
3. [処理対象の決定](#3-処理対象の決定)
4. [ステージ設計](#4-ステージ設計)
5. [データモデル](#5-データモデル)
6. [LLM呼び出し設計](#6-llm呼び出し設計)
7. [冪等性・失敗時の扱い](#7-冪等性失敗時の扱い)
8. [実行と設定](#8-実行と設定)
9. [受入基準](#9-受入基準)
10. [本単位でやらないこと](#10-本単位でやらないこと)

---

## 1. スコープ

**適時開示から、マクロテーマ（L1/L2）を付与して蓄積するまで。**

```
TDnet → 原本保存 → テキスト化 → LLMでテーマ付与 → BigQuery
```

- ウォッチ企業・関連企業の関係（peer/partner/customer）は**扱わない**。ペンディング中のため。
- 企業アクション抽出、示唆マッピング、レポート生成も**扱わない**。
- 本単位の成果物は「開示にマクロテーマが付いた状態のテーブル」である。

**この単位で検証したいこと**

- 15テーマ＋85サブテーマの分類体系が、実際の開示本文に対して機能するか。
- `other` と L2 null の発生率はどの程度か。
- 1開示あたりの実トークン量とコスト。

## 2. 全体フローと既存コードの再利用

`notebook/` に既存の実装がある。**書き直さず、関数として再利用する。**

| ステージ | 既存コード | 再利用方針 |
|---|---|---|
| 取得 | `notebook/fetch_tdnet_metadata.py` | `fetch_tdnet_metadata_for_date()` / `download_pdfs_for_date()` をそのまま使う |
| テキスト化 | `notebook/tdnet_pdf_preprocessing.py` | `normalized.md` と `candidate_evidence_spans.jsonl` の生成ロジックを使う |
| テーマ付与 | なし | 新規実装 |
| ロード | なし | 新規実装 |

既存コードはColab前提（`ROOT_DIR = "/content/drive/..."`、`_ensure_dependency()` による実行時pip）で書かれている。**移植時の変更は次の3点に限定し、処理ロジックには触れない。**

1. パス定数を設定から注入する（8章）
2. `_ensure_dependency()` を削除し、依存は `requirements.txt` で解決する
3. 標準出力の `print` を構造化ログに置換する

**依存に `cryptography` を必ず含める。** TDnetのPDFにはAES暗号化されたものが混じり、これがないと `pypdf` / `pymupdf` 系で開けずテキスト化が失敗する。件数が少ないため、握り潰されると気づきにくい。

## 3. 処理対象の決定

### 3.1 企業の絞り込み

- `data/master/dim_company_seed.csv`（100社）を**単なるウォッチリストとして使う**。関係区分は参照しない。
- TDnetの `code` 先頭4桁で突合し、一致しない開示は破棄する。
- **PDFをダウンロードする前に突合する。** 全件ダウンロードすると週1.5〜3.5GBを消費する（実測ベース）。100社に絞れば週30〜85MBに収まる。

### 3.2 `source_type` の絞り込み — 本単位では行わない

- 04§3はMVPの処理対象を期中開示（`timely_disclosure` / `forecast_revision`）に限定している。**本単位ではこの絞り込みを適用しない。**
- 判断根拠は、[本文全件精読](../99_feedback/2026-09-01_disclosure_body_verification.md)§9の実測である。100社の適時開示236件の本文を全件取得し、マスタの `typical_expressions` 239語の出現を測定した。

| `source_type` | 件数 | マクロ語あり | 率 | 平均文字数 |
|---|---|---|---|---|
| `timely_disclosure` | 119 | 41 | 34.5% | 1,677 |
| `forecast_revision` | 16 | 8 | 50.0% | 1,516 |
| `earnings` | 74 | 71 | **95.9%** | 13,855 |
| `earnings_presentation` | 27 | 25 | **92.6%** | 11,703 |
| 合計 | 236 | 145 | 61.4% | |

- **決算資料の含有率が9割超であるのに対し、期中開示は34.5%に留まる。** マクロテーマ付与という目的に対しては、04§3が定めた優先順位（期中開示を主、決算資料をPhase 2）が逆転する。
- ただし**期中開示も3件に1件はマクロ要因を含む**ため、除外はしない。`forecast_revision` は50.0%であり、業績予想の修正理由としてマクロ要因が書かれるためである。
- **タイトルでは判定できない。** 16テーマの語は開示タイトルにほぼ出現せず（全9,372件で最大18件）、本文を読んで初めて判定できる。
- したがって本単位は全 `source_type` を対象とする。
- `source_type` の判定自体は行い、テーマ出現率をソース別に集計できるようにする。判定は正規表現で行う（実測で98.2%が分類可能）。

### 3.3 想定件数

100社・全 `source_type` で、22営業日あたり219件（実測）。月間約290件。

| `source_type` | 月間 | 1件あたり分量 |
|---|---|---|
| `timely_disclosure` | 約137 | 1〜3ページ |
| `earnings` | 約97 | 20〜40ページ |
| `earnings_presentation` | 約35 | 30〜50ページ |
| `forecast_revision` | 約23 | 1〜2ページ |

## 4. ステージ設計

層は05§1の6層に従う。本単位では `report` 層を作らない。

### 4.1 ingest（original層）

```
入力: 対象日付
1. TDnet一覧を取得（fetch_tdnet_metadata_for_date）
2. JPXマスタを銘柄コードで突合し、業種・市場商品区分・issuer_kind を付与
3. source_type を正規表現で判定し、メタデータに付与
4. PDFを取得し GCS original/dt=YYYY-MM-DD/ へ保存（絞り込みをしない）
5. メタデータを BQ raw.tdnet_metadata へ
```

- **取得段階で確定できる分類はすべてここで付与する。** 業種・市場商品区分・`issuer_kind`・`source_type` は銘柄コード／銘柄名／タイトルだけで決定でき、LLMを必要としない。後段で計算し直さない。
- **企業や業種による絞り込みはここで行わない。** original層は「その日の全開示」という完全な資産にする。絞り込みは extract 段階（4.3）の責務である。対象の定義は今後も変わるため、変えるたびに取得と前処理をやり直す構成にしてはならない。

- 原本は**取得したバイト列のまま**保存する。意味を加えない（05§1）。
- 保存パスは `original/dt=2026-09-01/{disclosure_id}.pdf`。

### 4.2 transform（raw層）

```
入力: original層のPDF
1. PDFをテキスト化（tdnet_pdf_preprocessing のロジック）
2. normalized.md と candidate_evidence_spans を生成
3. GCS raw/dt=YYYY-MM-DD/{disclosure_id}/ へ保存
4. 全文を BQ raw.disclosure_text へ
```

- 既存実装は `document_blocks.jsonl` / `document_tables.jsonl` / `evidence_package.json` / `processing_report.json` を出力する。**本単位で必要なのは `normalized.md` と `candidate_evidence_spans.jsonl` の2つ**であり、他は保存するがBQには載せない。
- 暗号化PDFは復号して処理する。復号できない場合は `status = failed` で記録し、次の開示へ進む。

### 4.3 extract（processed層）

```
入力: raw層のテキスト、dim_macro_theme
0. issuer_kind / jpx_sector_17 / source_type で対象を絞り込む
1. 本文を先頭から一定トークンで打ち切る
2. LLMを1開示1回呼び、structured output でテーマを取得
3. schema validation とコード検証（マスタに存在するか）
4. BQ processed.theme_extraction へ（生のLLM出力とvalidation結果を含む）
```

### 4.4 load（product層）

```
入力: processed層
1. validation を通過した行を product の2テーブルへ MERGE
2. 実行結果を ops_run_log へ1行
```

## 5. データモデル

### 5.1 マスタ（CSVからロード）

| テーブル | 元ファイル | 件数 |
|---|---|---|
| `dim_macro_theme` | `data/master/dim_macro_theme_seed.csv` | 101（L1 16＋L2 85。`level` 列で判別） |
| `dim_company` | `data/master/dim_company_seed.csv` | 100 |

CSVは UTF-8 with BOM。**読み込みは `encoding='utf-8-sig'` を指定する。** BOMを除去しないと1列目のカラム名が `﻿company_id` となり、突合が全件失敗する。

### 5.2 ファクト

**`fact_disclosure`** — 開示1件1行

```text
disclosure_id       STRING  TDnetの開示ID
company_id          STRING  証券コード（4桁）
company_name        STRING
disclosure_datetime TIMESTAMP
title               STRING
source_type         STRING  timely_disclosure / earnings / earnings_presentation / forecast_revision
original_uri        STRING  GCS上の原本パス
text_uri            STRING  GCS上のテキストパス
page_count          INT64
char_count          INT64
gate_passed         BOOL    ルールゲートを通過したか（6.5）
status              STRING  ok / failed
```

**`fact_disclosure_theme`** — 開示 × テーマ

```text
theme_mention_id    STRING  SHA256(disclosure_id + ':' + seq) の先頭16桁
disclosure_id       STRING
theme_code          STRING  L1。必須
subtheme_code       STRING  L2。null許容
direction           STRING  up / down / neutral / unknown
evidence_text       STRING  根拠となる原文
evidence_offset     INT64   normalized.md 中の位置
extraction_confidence FLOAT64
taxonomy_version    STRING
extracted_at        TIMESTAMP
```

- **テーマは開示に付与する。** 04§5は `fact_theme_mapping`（ファクト×テーマ）を定義しているが、本単位ではファクト抽出を行わないため、開示に直接付ける。
- **将来ファクト抽出を追加する際は、本テーブルに `fact_id` 列を追加して紐づける。** テーブルを作り直さずに移行できるよう、`theme_mention_id` を主キーとして独立させている。
- 物理設計は `disclosure_id` でクラスタリング、`fact_disclosure` は `DATE(disclosure_datetime)` でパーティション（05§5）。

## 6. LLM呼び出し設計

### 6.1 方針

- **1開示につき1回**（04§6.1）。
- `temperature = 0`。再現性のため。
- 入力は本文とマスタ定義のみ。過去データや他社の情報は文脈に入れない。トークン量が本文長だけで決まるようにするため。

### 6.2 プロンプトに載せるもの

- L1の全16行（`theme_code` / `name` / `definition` / `includes` / `excludes`）
- L2の全85行（`theme_code` / `subtheme_code` / `name` / `typical_expressions`）
- 開示本文（打ち切り済み）

**`excludes` を必ず含める。** 判定が揺れるのは境界例であり、`commodity_price` と `import_price`、`geopolitics` と `trade_policy`、`financial_conditions` と `asset_price` は excludes でしか切り分けられない。

### 6.3 出力スキーマ

```json
{
  "themes": [
    {
      "theme_code": "commodity_price",
      "subtheme_code": "grain",
      "direction": "up",
      "evidence_text": "原材料である小麦の価格が高騰しており",
      "extraction_confidence": 0.94
    }
  ]
}
```

- `theme_code` は必須。マスタに存在しない値は validation で弾く。
- `subtheme_code` は **null 許容**。確信を持って特定できない場合は null を返させる（04§4.1）。
- **マクロ要因の記述がない開示は `themes: []` を返させる。** 無理に付与させない。
- 1開示あたりのテーマ数に上限は設けないが、L1は最大3件とする（04§4.1）。

### 6.4 レイヤー混同の防止

プロンプトで明示的に禁止する。

- 企業への影響（原材料コスト上昇、利益率低下）を `macro_theme` に入れない
- 企業アクション（値上げ、設備投資）を `macro_theme` に入れない
- これらは各テーマの `excludes` にも記載済みである

### 6.5 ルールゲート

LLMを呼ぶ前に、**マクロ語彙が本文に1つも出現しない開示を除外する。**

```
本文テキスト
    ↓
[ゲート] dim_macro_theme / dim_macro_subtheme の typical_expressions（239語）と照合
    ↓                              ↓
  1語も出現しない              1語以上出現する
    ↓                              ↓
 LLMを呼ばない                 LLMで分類・evidence・direction
 themes = [] で確定
```

**設計上の制約**

- **ゲートは「除外」にのみ用い、「付与」には用いない。** 語の出現はテーマの存在を意味しない。実測では `commodity_price` が138件ヒットしたが、「金」「銅」等の一般語による誤検出を多く含む。**どのテーマかを決められるのはLLMだけである。**
- ゲート語彙はマスタの `typical_expressions` をそのまま使う。専用の辞書を別に持たない。マスタを更新すればゲートも追従する。
- **除外した開示も `fact_disclosure` には記録する。** `themes` が空であることと、処理していないことを区別できるようにするため。`gate_passed` 列を持たせる。

**期待される削減**

実測（§3.2）から、期中開示119件のうち78件（65.5%）、全236件のうち91件（38.6%）が除外対象になる。決算資料はほぼ全件がゲートを通過する。

**較正期間を設ける**

- **ゲートで落とした開示は、LLM出力が存在しないため事後検証できない。**
- したがって稼働開始から一定期間は、ゲートで落とす対象にも**LLMを呼び、ゲート判定と突合する**。ゲートが落とした開示にLLMがテーマを付けた場合、それは語彙の不足を示す。
- 較正が済むまでゲートによる除外を有効化しない。

### 6.6 コスト見積り

| 項目 | 見積り |
|---|---|
| 対象開示 | 月290件（ゲート適用後は約180件） |
| マスタ定義（固定） | 約4,000トークン/回 |
| 本文（打ち切り後） | 平均約6,000トークン/回 |
| 月間入力 | 約290万トークン |
| 月額 | 安価モデルで数百円 |

上限1万円に対して十分な余裕がある。**マスタ定義が毎回4,000トークン載る点に注意する。** 開示本文が短い期中開示では、入力の大半がマスタ定義になる。プロンプトキャッシュが使えるモデルであれば適用する。

## 7. 冪等性・失敗時の扱い

- 書き込みはすべて `MERGE`。`INSERT` を使わない（05§7.8）。
- `theme_mention_id` は `SHA256(disclosure_id + ':' + seq)` で決定的に生成する。同一開示の再処理で同じIDが再現し、行が増えない。
- validation 失敗時は**1回だけリトライ**し、エラー内容をプロンプトに付加する。2回失敗したら `status = failed` で記録し、ジョブは継続する（04§7.2）。
- 再処理は日付範囲を引数に取る。起点は常に `original` 層である。

**Human Review は作らない**（04§7.2）。低confidenceのレコードはフラグを立てるのみとし、SQLで確認できる状態にする。

## 8. 実行と設定

### 8.1 CLI

```bash
python -m pipeline --stage=ingest    --from=2026-09-01 --to=2026-09-07
python -m pipeline --stage=transform --from=2026-09-01 --to=2026-09-07
python -m pipeline --stage=extract   --from=2026-09-01 --to=2026-09-07
python -m pipeline --stage=load      --from=2026-09-01 --to=2026-09-07
python -m pipeline --stage=all       --from=2026-09-01 --to=2026-09-07
```

- ステージを個別に実行できること。**extract のやり直しが最も頻繁に発生する**（プロンプト調整・マスタ改定）ため、ingest / transform を再実行せずに済む構成が必須である。

### 8.2 設定

環境変数で注入する。既存コードのパス定数はここから受け取る。

```text
GCP_PROJECT, GCS_BUCKET_ORIGINAL, GCS_BUCKET_RAW,
BQ_DATASET_RAW, BQ_DATASET_PROCESSED, BQ_DATASET_PRODUCT,
LLM_MODEL, LLM_MAX_INPUT_TOKENS, LLM_API_KEY(Secret Manager),
MASTER_DIR
```

### 8.3 ローカル実行

**GCPなしでローカル実行できること。** 検証を回すために必須である。GCS/BQの代わりにローカルディレクトリとJSONLへ書き出すモードを持たせる。

```bash
python -m pipeline --stage=all --from=2026-09-01 --to=2026-09-07 --local --out=./data
```

## 9. 受入基準

- 指定期間の100社の開示が取得され、テキスト化され、テーマが付与されて `fact_disclosure_theme` に入っていること。
- 同一期間を再実行しても行数が増えないこと。
- 以下が数値で出ること。これが本単位の主目的である。

| 指標 | 見方 |
|---|---|
| テーマ付与率（`themes` が空でない開示の割合） | `source_type` 別に見る。決算資料で高く、期中開示で低いはず |
| `other` の割合 | 高ければ分類体系の欠落 |
| L2 null の割合 | L1別に見る。特定テーマで高ければL2定義の不足 |
| L1別の出現件数 | 全く出現しないテーマは定義か対象企業のミスマッチ |
| 1開示あたりの実トークン量とコスト | 6.5の見積りとの差 |
| `status = failed` の件数と理由 | 暗号化PDF・テキスト化失敗の実数 |
| ゲート除外率と、較正期間中の取りこぼし | ゲートが落とした開示にLLMがテーマを付けた件数。0でなければ語彙不足（6.5） |

## 10. 本単位でやらないこと

- ウォッチ企業と関連企業の関係（peer/partner/customer）の付与
- 企業アクション（`company_action`）・定量値の抽出
- 自社への示唆（`fact_implication`）のマッピング
- レポート生成と配信
- Terraform によるインフラ構築、Cloud Run / Scheduler での自動実行
- Human Review の仕組み

**軽量モデル・小型LLMへの置き換えも行わない。** 現時点でLLMコストは月数百円であり、上限1万円に対して制約になっていない。また置き換えの可否は、LLM出力を正解データとして精度比較して初めて判断できる。**正解が存在しない段階で軽量化すると、精度を語れないまま構成だけが複雑になる。** 受入基準（9章）の数値が出た後に検討する。

**上記のうちインフラ構築は、本単位の検証が済んでから着手する。** テーマ分類体系が機能するかが未検証の段階でインフラを組むと、分類体系の作り直しが発生した場合に手戻りが大きい。
