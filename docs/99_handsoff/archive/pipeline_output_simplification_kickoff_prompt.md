# TDnetパイプライン出力シンプル化プロジェクト キックオフプロンプト

## 関連リンク

- [パイプライン出力シンプル化設計](pipeline_output_simplification_design.md)
- [汎用本文メタデータ・エンリッチメント設計](generic_body_metadata_enrichment_design.md)
- [半導体マクロイベント抽出設計](semiconductor_macro_event_extraction_design.md)

## 使い方

以下の「プロンプト本文」を、新しいAgentセッションへそのまま貼り付けて使用する。

最初のセッションでは調査と計画だけを行い、コード変更は計画承認後に開始することを推奨する。

---

## プロンプト本文

```text
対象リポジトリ:
- /Users/pgin/Git/020_prop_candidates
- /Users/pgin/Git/021_事業マクロ経済翻訳アナリスト、事業経営ダッシュボード、経営企画部向けマクロBI、半導体

プロジェクト名:
TDnetパイプライン出力シンプル化

背景:
TDnetパイプラインの処理工程自体は妥当ですが、PDF前処理以降でcanonicalデータ、CSV/JSONL/Markdown projection、summary、failed、report、日次版、全期間版、debug/legacy成果物がそれぞれ永続化されています。

その結果、1文書・1工程あたりのファイル数が多く、後段の入力スキーマ、ファイル突合、status、Nullable、version、日次/all整合性が複雑になっています。

現行フロー:
1. metadata・PDF取得
   /Users/pgin/Git/020_prop_candidates/notebook/fetch_tdnet_metadata.py
2. タイトル等のメタデータエンリッチメント
   /Users/pgin/Git/020_prop_candidates/notebook/classify_real_estate_titles.py
3. PDF前処理
   /Users/pgin/Git/020_prop_candidates/notebook/tdnet_pdf_preprocessing.py
4. 汎用本文メタデータエンリッチメント
   /Users/pgin/Git/021_事業マクロ経済翻訳アナリスト、事業経営ダッシュボード、経営企画部向けマクロBI、半導体/notebook/generic_body_metadata_enrichment.py
5. 半導体マクロイベント抽出
   /Users/pgin/Git/021_事業マクロ経済翻訳アナリスト、事業経営ダッシュボード、経営企画部向けマクロBI、半導体/docs/02_data_pipeline/semiconductor_macro_event_extraction_design.md

プロジェクト設計:
/Users/pgin/Git/021_事業マクロ経済翻訳アナリスト、事業経営ダッシュボード、経営企画部向けマクロBI、半導体/docs/02_data_pipeline/pipeline_output_simplification_design.md

目的:
処理工程と監査可能性を維持したまま、永続出力を原則として次の2種類へ整理してください。

1. 各工程のcanonical payload
2. 全工程共通のrun manifest

CSV、Markdown、JSONL、日次/all集計、summary、failed、review queueは、canonical payloadとmanifestから再生成できるview/exportへ変更します。

重要な設計原則:
- 処理stageの責務分離は維持する。
- canonical、operational、projection、debugを明確に分ける。
- 各stageの後段入力は原則1 logical artifactにする。
- 日次版と全期間版を別の正本にしない。partition/query scopeで表現する。
- CSVは後段パイプラインの正本にしない。
- document_id、source_id、page、block/table ID、evidence ID、quoteを維持する。
- schema/rules/taxonomy/extraction versionを維持する。
- LLM model、prompt、token、cost等のprovenanceを維持する。
- remote object storageを前提とし、logical URIと物理URIを分離する。
- 020のコードを021からimportしない。接続はファイル契約だけにする。
- 不動産タイトル分類を半導体パイプラインの必須工程にしない。domain pluginとして分離する。
- producerとconsumerを同時に破壊的変更しない。
- converter、adapter、dual-write、比較検証を使って段階移行する。
- legacy出力停止前にロールバック経路を確保する。

目標logical artifacts:
1. disclosures
2. document_bundles
3. document_enrichments
4. semiconductor_macro_events
5. pipeline_run_documents

初期推奨:
- PDF前処理canonical:
  document_bundles/{disclosure_date}/{document_id}.document_bundle.json.gz
- 文書エンリッチメント:
  partitioned Parquet
- 半導体イベント:
  partitioned Parquet
- operational status:
  共通run manifest Parquet
- CSV/Markdown:
  on-demand export

削減候補:
- normalized.mdの常時保存
- candidate_evidence_spans.jsonl
- evidence_package.json
- 文書ごとの独立processing_report.json
- 各stageのsummary.csv
- 各stageのfailed.csv
- 各stageのdaily report
- すべての *_all 正本
- generic enrichmentの詳細JSONと主CSVの二重正本
- event JSON、JSONL、CSVの三重正本

削除してはいけない情報:
- 原文PDFへの参照
- document/source identity
- blocks/tablesとページ情報
- evidenceの追跡情報
- validation statusとerrors
- schema/version/provenance
- 0件、review、failed、部分失敗を区別する情報

まず実施すること:
Phase 0の調査と実装計画だけを行ってください。計画承認前にproducer/consumerコードを変更しないでください。

Phase 0の調査:
1. 現行artifact inventoryを作成する。
   - artifact名
   - producer
   - consumer
   - grain
   - format
   - canonical/projection/operational/debug/legacyの区分
   - required/optional
   - retention
   - 再生成可能性
2. producer-consumer dependency graphを作成する。
3. 同一情報の重複保持を特定する。
4. 現行の件数収支、status、error、version契約を整理する。
5. 廃止候補ごとに、利用consumerが存在しないか確認する。
6. remote storage、Parquet/query engine、small files制約を確認する。
7. 代表fixtureと旧・新同値比較方法を定義する。

Phase 0の成果物:
- current_artifact_inventory.md
- producer_consumer_dependency.md
- target_pipeline_contract.md
- pipeline_output_simplification_migration_plan.md
- ADR: JSON bundle vs Parquet
- test_and_equivalence_strategy.md

計画に必ず含めること:
- 020と021の変更境界
- PR/branchの分割
- common run manifest schema
- document bundle schema
- logical URI resolver
- converterとlegacy adapter
- dual-write期間
- consumer切替順序
- backfill範囲
- rollback
- legacy停止条件
- object数、容量、処理時間のbaseline/KPI

推奨実装順:
1. common run manifest
2. document bundle schemaとconverter
3. 020 PDF前処理のdual-write
4. 021 generic enrichmentのbundle reader
5. generic canonical dataset
6. semiconductor event canonical dataset
7. export/view layer
8. legacy停止とcompaction

受入基準:
- 各stageの必須入力は原則1 logical artifact。
- 各stageの必須永続出力はcanonical + common manifest。
- PDF前処理の文書当たり永続成果物はPDFを含め2 logical objects以下。
- 日次/allを別の正本として保持しない。
- CSV、Markdown、review queue、failed一覧を再生成できる。
- evidence追跡可能率100%。
- 旧・新payloadの意味的差分が検証されている。
- document/event件数が収支する。
- dual-write期間中に未解消のhigh severity差分がない。
- legacy consumerが0件になってから旧出力を停止する。

注意:
- 既存のユーザー変更を上書き・削除しないでください。
- 020/021の現行成果物を調査するときは、ソースコードを実契約の根拠にしてください。
- リモートストレージ上のデータが必要でアクセス方法が不明な場合は、推測せず確認してください。
- 不明な設計判断は、実装前に選択肢、推奨案、トレードオフを示してください。
- schemaを単に1つの巨大JSONへ統合するだけで終わらせず、後段consumer、検索、再処理、監査、small filesを含めて評価してください。

最初の回答:
1. タスク分析
2. 調査対象
3. 重要な設計判断
4. Phase 0の具体的な実施計画
5. ユーザー確認が必要な論点

コード変更はまだ行わないでください。
```

---

## キックオフ時に推奨する初期判断

プロンプト実行後、最初に次の3点を決めると進めやすい。

1. remote storageとquery engine
2. PDF canonicalの物理形式
3. common manifestの保存形式

推奨初期値:

```text
PDF canonical:
  per-document document_bundle.json.gz

document/event dataset:
  Parquet partitioned by disclosure_date

common run manifest:
  Parquet partitioned by run_date and stage

legacy compatibility:
  1 migration cycleのdual-write
```

Parquetやquery engineを現時点で導入しない場合でも、logical artifactとprojectionの分離は先行して実施できる。
