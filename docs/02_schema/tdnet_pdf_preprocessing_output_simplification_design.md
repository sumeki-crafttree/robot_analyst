# TDnet PDF前処理 出力シンプル化設計（検証フェーズ）

## 関連リンク

- [キックオフプロンプト](../99_prompt/tdnet_pdf_preprocessing_output_simplification_kickoff_prompt.md)
- [パイプライン出力シンプル化設計（本体プロジェクト）](pipeline_output_simplification_design.md)
- [パイプライン出力シンプル化 キックオフプロンプト（本体プロジェクト）](../99_prompt/pipeline_output_simplification_kickoff_prompt.md)
- [汎用本文メタデータ・エンリッチメント設計](generic_body_metadata_enrichment_design.md)
- 実装対象: `notebook/tdnet_pdf_preprocessing.py`（021リポジトリへ移植済み）
- 現行設計の原本（移植元、020リポジトリ）: `020_prop_candidates/docs/02_data-pipeline/tdnet_pdf_preprocessing_design.md`
- 本設計の対象外: `020_prop_candidates/src/prop_deal_tracker/tdnet_pdf_preprocessing/`（020側の本番実行パッケージ、今回は変更しない）

## 0. Claude Codeへの実行プロンプト

実行プロンプト本体は [キックオフプロンプト](../99_prompt/tdnet_pdf_preprocessing_output_simplification_kickoff_prompt.md) を参照。

## 1. 背景

現行実装（`020_prop_candidates/docs/02_data-pipeline/tdnet_pdf_preprocessing_design.md` 3章）は、1文書につき次の7ファイルを生成する。

```text
raw.pdf
normalized.md
document_blocks.jsonl
document_tables.jsonl
candidate_evidence_spans.jsonl
evidence_package.json
processing_report.json
```

`normalized.md` / `document_blocks.jsonl` / `evidence_package.json` は同じ本文・メタデータを異なる形式で重複保持している。さらに日次の `processing_summary.csv` / `processing_failed.csv` / `daily_processing_report.json` に加え、全期間版 `*_all` が別正本として存在する。

この課題に対しては、本体プロジェクトである [パイプライン出力シンプル化設計](pipeline_output_simplification_design.md) が既に、`document_bundles` / `document_enrichments` / `pipeline_run_documents` などのlogical artifactへ全面的に統合し、Parquet・remote storage・共通run manifestまで含めた大規模な移行を計画している。

一方、本設計はその大規模移行に着手する前段として、**最小コストで「1文書1ファイル化」が後段処理を壊さずに成立するか**だけを、`notebook/tdnet_pdf_preprocessing.py` 単体で検証することを目的とする。この検証結果は、本体プロジェクトのPhase 2「PDF document bundle」の入力になる。

## 2. 対象リポジトリとファイル

`fetch_tdnet_metadata.py` / `classify_real_estate_titles.py` / `tdnet_pdf_preprocessing.py` は020リポジトリから021リポジトリの`notebook/`へ移植済みで、内容は020側と完全に一致している（コード上の相違なし）。本設計は021側に置かれたファイルを対象とする。

```text
対象: /Users/pgin/Git/021_robot_analyst/notebook/tdnet_pdf_preprocessing.py
```

`ROOT_DIR` は移植後も変更していないため、実行時に読み書きするデータパス（Google Drive上の `git/prop_candidates/` 配下）は020側と共有されたままである。今回のタスクはコードの修正のみであり、`ROOT_DIR` や既存のデータ配置を変更しない。

020リポジトリの `notebook/tdnet_pdf_preprocessing.py` および `src/prop_deal_tracker/tdnet_pdf_preprocessing/` は、本タスクでは一切変更しない（読み取り専用の参照のみ許可する）。021へ移植した3ファイルと020原本の間で内容差分が生まれるが、その差分の扱い（同期方針、020側への還流の要否）は本タスクの対象外とし、別途判断する。

## 3. スコープ

### 対象

- `021_robot_analyst/notebook/tdnet_pdf_preprocessing.py` の修正のみ

### 対象外（今回は着手しない）

```text
020_prop_candidates/notebook/tdnet_pdf_preprocessing.py（変更しない、参照のみ）
020_prop_candidates/src/prop_deal_tracker/tdnet_pdf_preprocessing/（本番実行パッケージ）
021_robot_analyst/notebook/generic_body_metadata_enrichment.py（consumer側）
020側consumer（body_based_metadata_enrichment.py）
日次/全期間summary・failed・reportの形式変更
Parquet化、remote storage、共通run manifest
既存7ファイル出力の削除・停止
```

対象外の項目は、本検証の結果を踏まえた次フェーズ（別タスク）として扱う。

## 4. 設計原則

1. **非破壊**: 既存7ファイルの生成ロジック・内容・書式は変更しない。現状のconsumer（021の`generic_body_metadata_enrichment.py`、020の`body_based_metadata_enrichment.py`）は無停止で動き続ける。
2. **追加のみ**: 新規追加は `document_bundle.json` 1ファイルの生成と、その自己検証ロジックだけ。
3. **ロジック不変**: PDF抽出・レイアウト判定・quality計算・evidence抽出のロジックは変更しない。既存の中間データ（`blocks`, `tables`, `evidence_rows`, `metadata_obj`, `report`相当の値）をそのまま`document_bundle.json`へ詰め替える。
4. **検証可能**: bundleと既存7ファイルの間で意味的同値性を機械的に検証する自己チェック関数を実装し、日次レポートに結果件数を出す。
5. **小さく止める**: 今回のタスクは「bundleが正として成立し得るかの検証」であり、legacy出力の削除やsrc/への反映、020側への同期は行わない。

## 5. document_bundle.json スキーマ

出力パスは既存の文書ディレクトリ内に追加する。

```text
data/processed/tdnet_pdf_preprocessed/{yyyymmdd}/documents/{document_id}/
  raw.pdf                        # 既存・変更なし
  normalized.md                  # 既存・変更なし
  document_blocks.jsonl          # 既存・変更なし
  document_tables.jsonl          # 既存・変更なし
  candidate_evidence_spans.jsonl # 既存・変更なし
  evidence_package.json          # 既存・変更なし
  processing_report.json         # 既存・変更なし
  document_bundle.json           # 新規追加
```

### 5.1 トップレベル構造

| フィールド | 型 | 説明 |
|---|---|---|
| `bundle_schema_version` | string | 本bundle独自のスキーマ版。初期値 `"1.0.0"` |
| `document_id` | string | 既存と同じdocument_id |
| `source` | object | 5.2参照 |
| `preprocessing` | object | 5.3参照 |
| `blocks` | array\<object\> | `document_blocks.jsonl` の全行をそのまま配列化 |
| `tables` | array\<object\> | `document_tables.jsonl` の全行をそのまま配列化 |
| `domain_extensions` | object | 5.4参照 |
| `generated_at_utc` | string | ISO8601 UTC |

### 5.2 `source`（既存 `evidence_package.json.document_metadata` 相当を拡張）

| フィールド | 型 | 説明 |
|---|---|---|
| `source_id` | string | |
| `issuer_code` | string | |
| `issuer_name` | string | |
| `disclosure_date` | string | |
| `disclosure_time` | string | |
| `title` | string | |
| `document_url` | string | |
| `local_pdf_path` | string | 処理時の入力パス（既存`metadata_obj.local_pdf_path`） |
| `pdf_relative_path` | string | 同一ディレクトリ内の相対パス。固定値 `"raw.pdf"` |
| `sha256_hash` | string | |

### 5.3 `preprocessing`（既存 `processing_report.json` 相当）

既存の`processing_report.json`のフィールドをそのまま格納する。

```text
page_count
pdf_layout_type
page_layout_summary
text_char_count
block_count
table_count
evidence_span_count
document_text_extraction_quality
used_ocr
used_vision
ocr_candidate
processing_status
errors
```

### 5.4 `domain_extensions`

不動産ドメイン固有の情報は、汎用ブロック/テーブルと分離してこの配下に置く。021側の半導体パイプラインなど汎用layerだけを使うconsumerが、不動産固有evidenceを無視できるようにするため。[汎用本文メタデータ・エンリッチメント設計](generic_body_metadata_enrichment_design.md)が定義する「020の不動産向け `candidate_evidence_spans.jsonl` は汎用candidate生成に使用しない」という既存原則とも一致する。

| フィールド | 型 | 説明 |
|---|---|---|
| `real_estate_candidate_evidence` | array\<object\> | `candidate_evidence_spans.jsonl` の全行をそのまま配列化 |

### 5.5 サンプル

```json
{
  "bundle_schema_version": "1.0.0",
  "document_id": "20260501_6753_a1b2c3d4",
  "source": {
    "source_id": "tdnet-20260501-001",
    "issuer_code": "6753",
    "issuer_name": "シャープ",
    "disclosure_date": "2026-05-01",
    "disclosure_time": "15:00",
    "title": "固定資産の譲渡に関するお知らせ",
    "document_url": "https://www.release.tdnet.info/inbs/xxxx.pdf",
    "local_pdf_path": "/content/drive/MyDrive/git/prop_candidates/data/raw/tdnet_pdfs/20260501/6753_xxx.pdf",
    "pdf_relative_path": "raw.pdf",
    "sha256_hash": "a1b2c3d4..."
  },
  "preprocessing": {
    "page_count": 3,
    "pdf_layout_type": "doc_like",
    "page_layout_summary": {"doc_like": 3},
    "text_char_count": 8500,
    "block_count": 42,
    "table_count": 2,
    "evidence_span_count": 3,
    "document_text_extraction_quality": "high",
    "used_ocr": false,
    "used_vision": false,
    "ocr_candidate": false,
    "processing_status": "success",
    "errors": []
  },
  "blocks": [ { "block_id": "20260501_6753_a1b2c3d4_p001_b001", "...": "..." } ],
  "tables": [ { "table_id": "20260501_6753_a1b2c3d4_p002_t001", "...": "..." } ],
  "domain_extensions": {
    "real_estate_candidate_evidence": [
      { "evidence_id": "20260501_6753_a1b2c3d4_ev001", "...": "..." }
    ]
  },
  "generated_at_utc": "2026-05-01T06:10:00Z"
}
```

`normalized.md` はbundleへ格納しない。`source` + `preprocessing` + `blocks` + `tables` からいつでも再現できる（既存の `_build_normalized_markdown()` を呼べば同一内容が再生成できることを、後述7章の自己チェックで確認する）。

## 6. 設定フラグ

トップレベル設定に以下を追加する（既存の設定ブロックと同じ場所）。

```python
WRITE_LEGACY_ARTIFACTS = True   # 既存7ファイル。今回は常にTrueのまま運用する
WRITE_DOCUMENT_BUNDLE = True    # document_bundle.json の生成
RUN_BUNDLE_EQUIVALENCE_CHECK = True  # 生成直後にbundleと既存ファイルの同値性を検証する
BUNDLE_SCHEMA_VERSION = "1.0.0"
```

`WRITE_LEGACY_ARTIFACTS` は将来（次フェーズ）にFalseへ切替できるよう用意するが、**今回のタスクではTrue固定運用とし、Falseパスの動作保証や削除は行わない**。

## 7. 実装変更点

### 7.1 新規関数

```python
def _build_document_bundle(
    *,
    document_id: str,
    metadata_obj: Dict[str, Any],
    report: Dict[str, Any],
    blocks: List[Dict[str, Any]],
    tables: List[Dict[str, Any]],
    evidence_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """既存の中間データからdocument_bundle.jsonのdict表現を組み立てる。
    抽出ロジックは呼ばない。既存値の詰め替えのみ。"""


def _write_document_bundle(doc_dir: str, bundle: Dict[str, Any]) -> str:
    """document_bundle.json を書き込み、書き込んだパスを返す。"""


def _verify_bundle_equivalence(doc_dir: str) -> List[str]:
    """doc_dir配下のdocument_bundle.jsonと既存7ファイルを読み直し、
    意味的に同値であることを検証する。差分があれば人間が読める
    文字列のリストを返す（空リスト=一致）。

    検証内容:
      1. bundle["document_id"] が normalized.md front matter /
         evidence_package.json["document_metadata"]["document_id"] /
         processing_report.json["document_id"] と一致する
      2. bundle["blocks"] が document_blocks.jsonl の全行と
         順序・内容ともに一致する
      3. bundle["tables"] が document_tables.jsonl の全行と一致する
      4. bundle["domain_extensions"]["real_estate_candidate_evidence"] が
         candidate_evidence_spans.jsonl の全行と一致する
      5. bundle["preprocessing"] の各フィールドが processing_report.json の
         対応フィールドと一致する
      6. bundle["source"] の各フィールドが evidence_package.json
         ["document_metadata"] および normalized.md front matter の
         対応フィールドと一致する
      7. bundleのsource/preprocessing/blocks/tablesから
         既存の _build_normalized_markdown() を呼んで再生成した文字列が、
         ディスク上の normalized.md の内容とバイト単位で一致する
    """
```

### 7.2 `process_one_pdf()` への組み込み

既存の書き込み処理（`_write_jsonl(...)`, `evidence_package.json`書き込み, `processing_report.json`書き込み）はすべて残す。その直後に追加する。

```python
if WRITE_DOCUMENT_BUNDLE:
    bundle = _build_document_bundle(
        document_id=document_id,
        metadata_obj=metadata_obj,
        report=report,
        blocks=blocks,
        tables=tables,
        evidence_rows=evidence_rows,
    )
    _write_document_bundle(doc_dir, bundle)

bundle_mismatches: List[str] = []
if RUN_BUNDLE_EQUIVALENCE_CHECK and WRITE_DOCUMENT_BUNDLE:
    bundle_mismatches = _verify_bundle_equivalence(doc_dir)
    if bundle_mismatches:
        # loggerにdocument_idと差分を残す。処理自体は失敗させない
        # (既存7ファイルは既に正しく書き込み済みのため)
        print(f"[warn] bundle mismatch document_id={document_id}: {bundle_mismatches}")
```

戻り値の `result` dict（`day_summary_rows`に積まれるもの）に以下を追加する。

```python
"bundle_written": bool(WRITE_DOCUMENT_BUNDLE),
"bundle_mismatch_count": len(bundle_mismatches),
```

### 7.3 日次・全体レポートへの集計追加

`daily_processing_report.json` / `processing_report_all.json` に以下を追加する（既存フィールドは変更しない、追加のみ）。

```python
"bundle_written_count": ...,
"bundle_mismatch_count_total": ...,
```

## 8. 実装しないこと（明示的な非スコープ）

- `WRITE_LEGACY_ARTIFACTS = False` にした場合の動作確認・保証
- `document_bundle.json` の圧縮（`.json.gz`化）。まずは可読性優先でプレーンJSONとする
- `normalized.md` を bundleからのon-demand生成へ切り替えること（既存書き込みは残す）
- 020リポジトリ（`notebook/tdnet_pdf_preprocessing.py`、`src/prop_deal_tracker`）への同様の変更の反映・同期
- 021側`generic_body_metadata_enrichment.py`・020側`body_based_metadata_enrichment.py`など既存consumerコードの変更
- 日次/全期間ファイルの統合・Parquet化

## 9. 受け入れ基準

1. 既存7ファイルの内容が、変更前と比較してバイト単位で同一である
2. 代表的な複数レイアウト（`doc_like` / `slide_like` / `table_heavy` / `scanned_or_image`）の文書で `document_bundle.json` が生成される
3. `_verify_bundle_equivalence()` がこれらの代表文書すべてでdiffなし（空リスト）を返す
4. `daily_processing_report.json` に `bundle_written_count` / `bundle_mismatch_count_total` が追加され、値が処理件数と整合する
5. 021リポジトリに既存の自動テストがある場合、それらが壊れていない
6. `document_bundle.json` 1ファイルから、既存の`evidence_package.json`・`processing_report.json`・`document_blocks.jsonl`・`document_tables.jsonl`・`candidate_evidence_spans.jsonl`・`normalized.md`と同等の情報を欠落なく再構成できることを、上記equivalence checkで確認できる

## 10. 次フェーズ（本タスクでは着手しない、参考情報）

本検証で `document_bundle.json` が正として成立すると判断できた場合、次の順で段階移行する（別タスク）。

1. 021側 `generic_body_metadata_enrichment.py` をbundle読み込みに対応させる（既存7ファイル読み込みと並行対応、dual-read期間を設ける）
2. 020リポジトリ（`notebook/tdnet_pdf_preprocessing.py` および `src/prop_deal_tracker/tdnet_pdf_preprocessing/`）へ同様の変更を反映するかどうかを判断する。021と020の実装が分岐したままでよいか、同期が必要かをこの時点で決める
3. 020側consumer（`body_based_metadata_enrichment.py`）の対応要否を判断する
4. legacy consumerが0件になったことを確認してから `WRITE_LEGACY_ARTIFACTS` を `False` に切替
5. 日次/全期間ファイルの統合、共通run manifest、Parquet化は [パイプライン出力シンプル化設計](pipeline_output_simplification_design.md) のロードマップと合流させる
