# 開示分類のメタデータ化 リファクタ キックオフプロンプト

**種別**: 既存実装の修正（新規実装ではない）
**対象ファイル**: `notebook/fetch_tdnet_metadata.py` / `notebook/preprocess_disclosures.py` / `notebook/tag_macro_theme.py`
**含む修正**: ①開示分類のメタデータ化 ②`fetch_tdnet_metadata.py` へのログ機能追加（実装漏れ）
**関連**: [Colab検証環境 詳細設計](../01_design/02_colab_prototype_design.md) §3 / [初回実装のキックオフ](colab_macro_theme_tagging_kickoff_prompt.md)

## 背景

2026年9月7日のサンプル実行（`data/samples/macro_themes_20260907.jsonl`）で、ETFの日次基準価額開示が処理対象に混入していた。「SPDRゴールド・シェアに関する日々の開示事項」に `commodity_price/precious_metal` が付与されるなど、事業会社の開示ではないものにテーマが付いている。

原因は**分類情報がどの工程でも付与されていないこと**である。`jpx_sector_17` は各スクリプトが読み取るだけで、どこも書き込んでいない（常に空文字）。`source_type` は前処理側で毎回計算し直している。

## 使い方

以下の「プロンプト本文」を新しいセッションへ貼り付ける。**既存実装の修正であり、新規作成ではない。** 動いているコードを壊さないことを最優先とする。

---

## プロンプト本文

```text
対象リポジトリ: /Users/pgin/Git/021_robot_analyst

# 依頼

既存の3スクリプトを修正し、開示の分類をメタデータ段階で確定させる
リファクタを行ってください。新規実装ではなく既存コードの修正です。

## 読むもの

docs/01_design/02_colab_prototype_design.md の 3章（全体フローと責務分担）

この章に、なぜこの分担にするかの根拠が書いてあります。設計と矛盾する
実装をしないでください。

## 解決したい問題

2026年9月7日の実行結果 data/samples/macro_themes_20260907.jsonl に、
ETFの日次基準価額開示が混入しています。
「SPDRゴールド・シェアに関する日々の開示事項」に commodity_price/precious_metal
が付くなど、事業会社ではない発行体の開示にテーマが付与されています。

原因は分類情報がどこでも付与されていないことです。
- jpx_sector_17 は各スクリプトが読み取るだけで、書き込む処理が存在しない
- source_type は前処理側で毎回計算し直している

## 修正内容

### 1. notebook/fetch_tdnet_metadata.py

銘柄コードで data/master/jpx_listed_202606.xls を突合し、メタデータCSVに
以下5項目を付与してください。いずれもLLM不要で決定的に決まります。

  jpx_sector_17        17業種区分（コード突合）
  jpx_sector_33        33業種区分（コード突合）
  jpx_market_segment   市場・商品区分（コード突合）
  issuer_kind          operating_company / etf_etn / reit_fund
  source_type          タイトルの正規表現（実測98.2%）

issuer_kind の導出:
  JPXマスタの市場・商品区分を第一の根拠とする。
    "ETF・ETN"                                           → etf_etn
    "REIT・ベンチャーファンド・カントリーファンド・インフラファンド" → reit_fund
    それ以外                                              → operating_company

  JPXマスタに未収載の銘柄（実測69件・新規上場等）は、銘柄名の接頭辞で補う。
    Ｅ－ / Ｎ－  → etf_etn
    Ｒ－ / Ｉ－  → reit_fund
    それ以外     → operating_company

  実測9,372件で接頭辞とJPX市場区分は100%一致しました。ただし接頭辞のない
  銘柄にもETF・ETNが345件あるため、接頭辞だけでは取り切れません。
  両方を使ってください。

  source_type の判定ロジックは preprocess_disclosures.py に既にあります
  （classify_source_type）。これを移設し、前処理側からは削除してください。

  PDFは取得済みです。メタデータCSVだけを再生成できるようにしてください
  （PDFの再ダウンロードを走らせないこと）。

【ログ機能の追加】

  fetch_tdnet_metadata.py にはログ機能が入っていません。
  ログ機能を実装した際に、このファイルだけ対象から漏れていたためです。
  他の2本と同じ仕組みを移植してください。

  参照実装: notebook/preprocess_disclosures.py の以下
    LOG_DIR / SCRIPT_NAME 定数
    _log_path()    <LOG_DIR>/<日時>_<スクリプト名>.txt を返す
    _log_header()  ログ先頭に残す実行条件
    _Tee           標準出力とファイルの両方へ書き、毎回flushする

  ログの出力先とファイル名の規約は他2本と揃えてください。
  Driveの名前順が実行順になるよう、日時をファイル名の先頭に置きます。
  Colabはセッションが切れると標準出力が消えるため、Drive上に残すことが
  目的です。

  _log_header() はスクリプトごとに中身が変わります。取得スクリプトでは
  対象日付の範囲、取得件数、DOWNLOAD_PDFS の値など、後から実行条件を
  再現できる情報を残してください。

### 2. notebook/preprocess_disclosures.py

  - source_type の計算をやめ、メタデータCSVから読み取って転記するだけに
    してください。classify_source_type の呼び出しを削除します。
  - jpx_sector_17 / jpx_sector_33 / jpx_market_segment / issuer_kind も
    メタデータから読み取り、出力JSONLに含めてください。
  - これらがメタデータに欠けている場合はエラーにしてください。
    空文字で流すと、後段の絞り込みが黙って全件通過または全件除外になり、
    気づけません。
  - 【重要】絞り込みは一切しないでください。ETFもREITも含め、その日の
    全文書をテキスト化します。除外は次の工程の責務です。

### 3. notebook/tag_macro_theme.py

  ゲート判定より前に、対象の絞り込みを追加してください。

  絞り込み条件は設定として外に出し、コードに埋め込まないこと。

    TARGET_ISSUER_KINDS  = ["operating_company"]
    TARGET_SECTORS_17    = []      # 空なら全業種
    TARGET_SOURCE_TYPES  = ["timely_disclosure", "forecast_revision",
                            "earnings", "earnings_presentation"]

  対象外の文書は出力しないでください。「テーマが付かなかった」ことと
  「処理していない」ことを区別する必要があります。
  実行ログには対象件数と除外件数を出してください。

## 守ること

- 動いている処理ロジック（PDF解析、スパン抽出、GBNF、LLM呼び出し）には
  手を入れないでください。今回の修正はメタデータの受け渡しだけです。
- Colab前提（_ensure_dependency による実行時pip、ROOT_DIR定数）を維持。
- CSVはUTF-8 with BOM。encoding='utf-8-sig' を使用。
- 3スクリプトの実行モード（--sample / --date / --from-to）は変更しない。

## やらないこと

- ゲート語彙の修正（別タスクです。「金」「銀」の誤検出問題は本件と別に
  対応します）
- プロンプトの変更
- 新しいスクリプトの追加

## 完了条件

0. fetch_tdnet_metadata.py の実行ログが他2本と同じ規約でDriveに残ること
1. 2026年9月7日分のメタデータを再生成し、5項目が全件埋まっていること
2. 同日分の前処理を再実行し、ETFを含む全文書が出力されていること
3. 同日分の付与を再実行し、以下が成立すること
   - ETF・REITの開示が出力に含まれないこと
     （9月7日の結果にあった Ｅ－ワールド、Ｅ－ＷｉｓｄｏｍＴｒ、
       Ｅ－ＳＳＧＡ－ＳＩＮ、Ｅ－ＳＳＧＡＴＣ、Ｅ－インベスコＱＱＱ が
       消えていること）
   - 実行ログに対象件数と除外件数が出ていること
4. 修正前後で、事業会社の開示に対する付与結果が変わっていないこと
   （今回の修正は対象の絞り込みだけであり、判定ロジックは変えていないため）
```

---

## キックオフ時に推奨する初期判断

**1. `issuer_kind` の値の持ち方**

`operating_company` / `etf_etn` / `reit_fund` の3値で始める。PRO Market（170件）とグロース（1,737件）はいずれも事業会社であり、区別が必要になった時点で `jpx_market_segment` から導けるため、`issuer_kind` を細分化しない。

**2. JPXマスタの更新頻度**

`jpx_listed_202606.xls` は2026年6月末時点である。四半期ごとに更新される。**未収載銘柄が増え続けるため、接頭辞によるフォールバックは恒久的に必要である。** マスタ更新の運用は本タスクの範囲外とし、TODOとして残す。

**3. 既存メタデータCSVの扱い**

過去30日分のメタデータCSVは既に存在する。5項目を追加するには再生成が必要になるが、**PDFの再ダウンロードは不要**である。TDnet一覧の再取得のみで済むか、既存CSVへの後付け結合で済ませるかを最初に決める。後者のほうが速い。
