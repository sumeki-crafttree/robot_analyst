# TDnet PDF前処理 出力シンプル化（検証フェーズ） キックオフプロンプト

## 関連リンク

- [TDnet PDF前処理 出力シンプル化設計（検証フェーズ）](../02_data_pipeline/tdnet_pdf_preprocessing_output_simplification_design.md)
- [パイプライン出力シンプル化設計（本体プロジェクト）](../02_data_pipeline/pipeline_output_simplification_design.md)
- [パイプライン出力シンプル化 キックオフプロンプト（本体プロジェクト）](pipeline_output_simplification_kickoff_prompt.md)

## 使い方

以下の「プロンプト本文」を、新しいAgentセッションへそのまま貼り付けて使用する。

本タスクは、本体プロジェクト（パイプライン出力シンプル化）に着手する前段の小さな検証である。スコープを`021_robot_analyst/notebook/tdnet_pdf_preprocessing.py`単体に絞っているため、1セッションで実装から受け入れ確認まで完了できる想定。

---

## プロンプト本文

```text
対象リポジトリ:
- /Users/pgin/Git/021_robot_analyst

対象ファイル:
- /Users/pgin/Git/021_robot_analyst/notebook/tdnet_pdf_preprocessing.py

設計書:
- /Users/pgin/Git/021_robot_analyst/docs/02_data_pipeline/tdnet_pdf_preprocessing_output_simplification_design.md

プロジェクト名:
TDnet PDF前処理 出力シンプル化（検証フェーズ）

背景:
現行のtdnet_pdf_preprocessing.pyは1文書につき7ファイル（raw.pdf, normalized.md,
document_blocks.jsonl, document_tables.jsonl, candidate_evidence_spans.jsonl,
evidence_package.json, processing_report.json）を生成しており、正本projectionの
境界が曖昧になっている。本タスクは、これを1文書1ファイル（document_bundle.json）へ
統合できるかを、既存consumerを壊さない形で小さく検証する。

タスク:
設計書の「1〜9章」に従って notebook/tdnet_pdf_preprocessing.py を修正してください。

厳守事項:
- 変更対象は /Users/pgin/Git/021_robot_analyst/notebook/tdnet_pdf_preprocessing.py
  だけです。
- 020_prop_candidates配下のファイル（notebook/tdnet_pdf_preprocessing.py、
  src/prop_deal_tracker/tdnet_pdf_preprocessing/を含む）は読み取り専用の参照に
  限定し、変更・importしないでください。
- 021_robot_analyst/notebook/generic_body_metadata_enrichment.py など、
  既存consumerのコードも変更しないでください。
- 既存の7ファイル出力の内容・書式は変更しないでください（バイト単位で現状と同一）。
- 新規追加は document_bundle.json 1ファイルの生成と、bundleと既存ファイル群の
  意味的同値性を検証する自己チェック関数だけです。
- 既存のPDF抽出ロジック（PyMuPDF/pdfplumberの呼び出し、レイアウト判定、
  quality計算、evidence抽出）のロジック自体は変更しないでください。
  既存の中間データ（blocks/tables/evidence_rows/metadata_obj/report）を
  そのままbundleへ詰め替えるだけにしてください。
- ROOT_DIRや既存のデータパス設定は変更しないでください。

まず実施すること:
1. 設計書の理解確認（誤読していないか）
2. 変更するコード箇所の一覧
3. 実装計画
上記3点を提示し、認識が合っていることを確認してから実装に着手してください。

実装後:
- 設計書「9章 受け入れ基準」を1つずつ確認し、結果を報告してください。
- 代表的な複数レイアウト（doc_like / slide_like / table_heavy / scanned_or_image）
  のPDFで動作確認できない場合は、確認できなかった範囲と理由を明示してください。
- 実装方針に迷う判断がある場合は、実装前に選択肢と推奨案を提示してください。
- 020側への反映や既存consumerの改修は行わないでください（設計書10章の次フェーズ）。

最初の回答:
1. タスク分析
2. 設計書の理解確認
3. 変更するコード箇所の一覧
4. 実装計画
5. ユーザー確認が必要な論点

コード変更はまだ行わないでください。
```
