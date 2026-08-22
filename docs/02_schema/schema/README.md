# データパイプライン・スキーマ

## 関連リンク

- [汎用本文メタデータ・エンリッチメント設計](../generic_body_metadata_enrichment_design.md)
- [入力スキーマ解説](generic_body_metadata_enrichment_input_schema.md)
- [入力スキーマYAML正本](generic_body_metadata_enrichment_input_schema.yaml)
- [出力スキーマ解説](generic_body_metadata_enrichment_output_schema.md)
- [出力スキーマYAML正本](generic_body_metadata_enrichment_output_schema.yaml)

## 目次

1. [管理方針](#管理方針)
2. [versioning](#versioning)
3. [スキーマ一覧](#スキーマ一覧)
4. [レビュー状態](#レビュー状態)

---

## 管理方針

- 機械可読な契約は `.yaml` を正本とする。
- 業務上の意味、運用、例は対応する `.md` に記載する。
- enum、Nullable、型、制約はYAMLとMDで同期する。
- 下流互換を壊す変更は `schema_version` を更新する。
- 過去版を安易に削除せず、重要変更は対応するMDへ記録する。
- 実装はスキーマ正本に対してvalidationを行う。

## versioning

`schema_version` はSemantic Versioningを使う。

- major: カラム・成果物の削除、型変更、必須化、enumの意味変更
- minor: nullableな列・成果物・enum値の追加
- patch: 説明、例、互換性を壊さない制約明確化

分類ルールの変更は、出力構造とは別に `enrichment_version` で管理する。

## スキーマ一覧

| コンポーネント | 種別 | YAML正本 | 解説 |
|---|---|---|---|
| `generic_body_metadata_enrichment` | 入力 | `generic_body_metadata_enrichment_input_schema.yaml` | `generic_body_metadata_enrichment_input_schema.md` |
| `generic_body_metadata_enrichment` | 出力 | `generic_body_metadata_enrichment_output_schema.yaml` | `generic_body_metadata_enrichment_output_schema.md` |

## レビュー状態

初版は2026-07-16にレビュー・承認され、状態は `implemented` である。

- 設計: `../generic_body_metadata_enrichment_design.md`
- 入力契約: `generic_body_metadata_enrichment_input_schema.yaml/.md`
- 出力契約: `generic_body_metadata_enrichment_output_schema.yaml/.md`
- 実装: `../../../notebook/generic_body_metadata_enrichment.py`
