# -*- coding: utf-8 -*-

# ==========================================
# TDnet 汎用本文メタデータ・エンリッチメント
# Colab 1セル貼り付け実行対応
#
# 入力:
#   - data/original/tdnet_metadata_{yyyymmdd}.csv
#   - data/processed/tdnet_pdf_preprocessed/{yyyymmdd}/documents/{document_id}/...
#
# 出力:
#   - data/processed/tdnet_generic_body_metadata_enriched/
#
# 契約:
#   - docs/02_data_pipeline/generic_body_metadata_enrichment_design.md
#   - docs/02_data_pipeline/schema/generic_body_metadata_enrichment_*_schema.yaml
# ==========================================

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# -----------------------------
# 0) 実行設定
# -----------------------------
ROOT_DIR = os.environ.get(
    "GENERIC_ENRICHMENT_ROOT_DIR",
    "/content/drive/MyDrive/git/prop_candidates/",
)
METADATA_ROOT_DIR = os.environ.get(
    "GENERIC_ENRICHMENT_METADATA_ROOT",
    os.path.join(ROOT_DIR, "data/original"),
)
PREPROCESSED_ROOT_DIR = os.environ.get(
    "GENERIC_ENRICHMENT_PREPROCESSED_ROOT",
    os.path.join(ROOT_DIR, "data/processed/tdnet_pdf_preprocessed"),
)
OUTPUT_ROOT_DIR = os.environ.get(
    "GENERIC_ENRICHMENT_OUTPUT_ROOT",
    os.path.join(ROOT_DIR, "data/processed/tdnet_generic_body_metadata_enriched"),
)

START_DATE = ""  # YYYY-MM-DD or YYYYMMDD
END_DATE = ""  # YYYY-MM-DD or YYYYMMDD
MAX_DOCUMENTS: Optional[int] = None
RUN_SELF_CHECKS = True
SELF_CHECK_ONLY = False

SCHEMA_VERSION = "1.0.0"
ENRICHMENT_VERSION = "2026-07-16.001"
ENRICHMENT_METHOD = "rule_based"
OUTPUT_ENCODING = "utf-8"
CSV_ENCODING = "utf-8-sig"
MAX_DETAIL_EVIDENCE = 20
MAX_CSV_EVIDENCE_IDS = 5
MAX_EVIDENCE_CHARS = 2000
MAX_EVIDENCE_PREVIEW_CHARS = 300
HIGH_VALUE_DOCUMENT_TYPES = {
    "earnings_release",
    "earnings_presentation",
    "forecast_revision",
    "business_plan",
    "ma_restructuring",
    "business_alliance",
    "capex_fixed_assets",
    "impairment",
}
LOW_VALUE_DOCUMENT_TYPES = {
    "dividend_shareholder_return",
    "governance_personnel",
}


# -----------------------------
# 1) enum
# -----------------------------
DOCUMENT_TYPES = {
    "earnings_release",
    "earnings_presentation",
    "forecast_revision",
    "operating_update",
    "business_plan",
    "dividend_shareholder_return",
    "financing_capital_policy",
    "ma_restructuring",
    "business_alliance",
    "capex_fixed_assets",
    "impairment",
    "legal_regulatory",
    "governance_personnel",
    "sustainability",
    "other",
}
TOPIC_TAGS = {
    "performance",
    "outlook",
    "demand_sales",
    "pricing",
    "costs",
    "foreign_exchange",
    "inventory",
    "supply_chain",
    "investment_capacity",
    "portfolio_change",
    "partnership",
    "capital_structure",
    "shareholder_return",
    "asset_impairment",
    "legal_compliance",
    "governance_organization",
    "sustainability",
    "other",
}
BUSINESS_EVENT_TYPES = {
    "demand_change",
    "price_change",
    "cost_change",
    "capacity_change",
    "product_service_change",
    "market_entry_exit",
    "acquisition_disposal",
    "partnership",
    "restructuring",
    "supply_disruption",
    "workforce_change",
    "other",
}
FINANCIAL_IMPACT_TYPES = {
    "revenue",
    "operating_profit",
    "ordinary_profit",
    "net_income",
    "cash_flow",
    "assets",
    "liabilities",
    "equity",
    "capex",
    "dividend",
    "guidance",
}
IMPACT_DIRECTIONS = {"positive", "negative", "mixed", "neutral", "unclear"}
ACTUAL_OR_FORECAST_VALUES = {"actual", "forecast", "both", "unclear", "not_applicable"}
TIME_HORIZONS = {
    "immediate",
    "current_period",
    "next_period",
    "medium_term",
    "multiple",
    "unclear",
    "not_applicable",
}
DOWNSTREAM_PRIORITIES = {"high", "medium", "low", "skip"}
CANDIDATE_STAGES = {"body_supported", "body_weak", "body_unclassified", "needs_review"}
TEXT_QUALITIES = {"high", "medium", "low"}
MAIN_STATUSES = {"success", "needs_review", "failed_validation"}
SUMMARY_STATUSES = MAIN_STATUSES | {"failed"}


# -----------------------------
# 2) ルールレジストリ
# -----------------------------
@dataclass(frozen=True)
class Rule:
    rule_id: str
    target_field: str
    target_value: str
    keywords: Tuple[str, ...]
    negative_keywords: Tuple[str, ...] = ()
    priority: int = 100


DOCUMENT_TYPE_RULES: Tuple[Rule, ...] = (
    Rule("document_type.forecast_revision.001", "document_type", "forecast_revision", ("業績予想の修正", "業績予想修正", "通期予想の修正", "予想値の修正"), priority=10),
    Rule("document_type.earnings_release.001", "document_type", "earnings_release", ("決算短信", "四半期決算短信", "通期決算短信"), priority=20),
    Rule("document_type.earnings_presentation.001", "document_type", "earnings_presentation", ("決算説明資料", "決算説明会資料", "決算補足資料", "financial results presentation"), priority=30),
    Rule("document_type.operating_update.001", "document_type", "operating_update", ("月次売上", "月次業績", "受注高", "月次概況", "主要kpi"), priority=40),
    Rule("document_type.business_plan.001", "document_type", "business_plan", ("中期経営計画", "中期事業計画", "経営計画", "事業方針"), priority=50),
    Rule("document_type.ma_restructuring.001", "document_type", "ma_restructuring", ("株式取得", "株式譲渡", "事業譲渡", "会社分割", "合併", "子会社化", "組織再編", "m&a"), priority=60),
    Rule("document_type.business_alliance.001", "document_type", "business_alliance", ("業務提携", "資本業務提携", "共同開発", "戦略的提携", "合弁会社"), priority=70),
    Rule("document_type.capex_fixed_assets.001", "document_type", "capex_fixed_assets", ("設備投資", "新工場", "工場新設", "生産能力増強", "固定資産の取得", "固定資産の譲渡"), priority=80),
    Rule("document_type.impairment.001", "document_type", "impairment", ("減損損失", "減損処理", "事業損失", "特別損失", "引当金"), priority=90),
    Rule("document_type.financing_capital_policy.001", "document_type", "financing_capital_policy", ("第三者割当増資", "公募増資", "新株予約権", "社債発行", "資金借入", "資本政策"), priority=100),
    Rule("document_type.dividend_shareholder_return.001", "document_type", "dividend_shareholder_return", ("剰余金の配当", "配当予想", "自己株式の取得", "自己株式の消却", "株主還元"), priority=110),
    Rule("document_type.legal_regulatory.001", "document_type", "legal_regulatory", ("訴訟", "行政処分", "課徴金", "法令違反", "不正アクセス", "製品回収"), priority=120),
    Rule("document_type.governance_personnel.001", "document_type", "governance_personnel", ("代表取締役の異動", "役員人事", "人事異動", "定款の変更", "コーポレートガバナンス"), priority=130),
    Rule("document_type.sustainability.001", "document_type", "sustainability", ("サステナビリティ", "温室効果ガス", "脱炭素", "人権方針", "気候変動"), priority=140),
)

TOPIC_RULES: Tuple[Rule, ...] = (
    Rule("topic.performance.001", "topic_tags", "performance", ("売上高", "営業利益", "経常利益", "当期純利益", "業績")),
    Rule("topic.outlook.001", "topic_tags", "outlook", ("業績予想", "見通し", "ガイダンス", "予想値")),
    Rule("topic.demand_sales.001", "topic_tags", "demand_sales", ("需要", "販売数量", "受注", "売上", "出荷")),
    Rule("topic.pricing.001", "topic_tags", "pricing", ("価格改定", "値上げ", "販売価格", "価格転嫁", "単価")),
    Rule("topic.costs.001", "topic_tags", "costs", ("原材料価格", "原燃料", "エネルギーコスト", "物流費", "人件費", "コスト")),
    Rule("topic.foreign_exchange.001", "topic_tags", "foreign_exchange", ("為替", "円安", "円高", "usd/jpy", "ドル円")),
    Rule("topic.inventory.001", "topic_tags", "inventory", ("在庫", "棚卸資産", "在庫調整", "デストッキング")),
    Rule("topic.supply_chain.001", "topic_tags", "supply_chain", ("供給制約", "サプライチェーン", "物流混乱", "納期", "調達難")),
    Rule("topic.investment_capacity.001", "topic_tags", "investment_capacity", ("設備投資", "生産能力", "新工場", "増産", "稼働率")),
    Rule("topic.portfolio_change.001", "topic_tags", "portfolio_change", ("事業譲渡", "事業撤退", "買収", "子会社化", "ポートフォリオ")),
    Rule("topic.partnership.001", "topic_tags", "partnership", ("業務提携", "共同開発", "合弁", "パートナーシップ")),
    Rule("topic.capital_structure.001", "topic_tags", "capital_structure", ("増資", "社債", "借入", "自己資本", "資本政策")),
    Rule("topic.shareholder_return.001", "topic_tags", "shareholder_return", ("配当", "自己株式", "株主還元")),
    Rule("topic.asset_impairment.001", "topic_tags", "asset_impairment", ("減損", "特別損失", "評価損")),
    Rule("topic.legal_compliance.001", "topic_tags", "legal_compliance", ("訴訟", "法令", "行政処分", "コンプライアンス")),
    Rule("topic.governance_organization.001", "topic_tags", "governance_organization", ("役員", "人事", "定款", "ガバナンス", "組織変更")),
    Rule("topic.sustainability.001", "topic_tags", "sustainability", ("サステナビリティ", "脱炭素", "温室効果ガス", "人権", "気候変動")),
)

BUSINESS_EVENT_RULES: Tuple[Rule, ...] = (
    Rule("business_event.demand_change.001", "business_event_types", "demand_change", ("需要増", "需要回復", "需要減", "需要低迷", "販売数量増", "販売数量減")),
    Rule("business_event.price_change.001", "business_event_types", "price_change", ("価格改定", "値上げ", "値下げ", "販売価格上昇", "販売価格下落")),
    Rule("business_event.cost_change.001", "business_event_types", "cost_change", ("原材料価格上昇", "原材料価格下落", "コスト増", "コスト減", "物流費上昇")),
    Rule("business_event.capacity_change.001", "business_event_types", "capacity_change", ("生産能力増強", "増産", "減産", "新工場", "工場閉鎖", "設備投資")),
    Rule("business_event.product_service_change.001", "business_event_types", "product_service_change", ("新製品", "新サービス", "生産終了", "販売終了")),
    Rule("business_event.market_entry_exit.001", "business_event_types", "market_entry_exit", ("市場参入", "新規参入", "事業撤退", "市場撤退")),
    Rule("business_event.acquisition_disposal.001", "business_event_types", "acquisition_disposal", ("買収", "株式取得", "事業譲渡", "株式譲渡", "固定資産の譲渡")),
    Rule("business_event.partnership.001", "business_event_types", "partnership", ("業務提携", "共同開発", "合弁会社", "資本業務提携")),
    Rule("business_event.restructuring.001", "business_event_types", "restructuring", ("構造改革", "組織再編", "会社分割", "事業再編")),
    Rule("business_event.supply_disruption.001", "business_event_types", "supply_disruption", ("供給停止", "供給制約", "物流混乱", "操業停止", "調達難")),
    Rule("business_event.workforce_change.001", "business_event_types", "workforce_change", ("人員削減", "希望退職", "採用拡大", "人員増強")),
)

FINANCIAL_IMPACT_RULES: Tuple[Rule, ...] = (
    Rule("financial.revenue.001", "financial_impact_types", "revenue", ("売上高", "売上収益", "営業収益")),
    Rule("financial.operating_profit.001", "financial_impact_types", "operating_profit", ("営業利益", "事業利益")),
    Rule("financial.ordinary_profit.001", "financial_impact_types", "ordinary_profit", ("経常利益",)),
    Rule("financial.net_income.001", "financial_impact_types", "net_income", ("当期純利益", "親会社株主に帰属する", "最終利益")),
    Rule("financial.cash_flow.001", "financial_impact_types", "cash_flow", ("キャッシュ・フロー", "キャッシュフロー", "フリーキャッシュフロー")),
    Rule("financial.assets.001", "financial_impact_types", "assets", ("総資産", "固定資産", "棚卸資産", "減損")),
    Rule("financial.liabilities.001", "financial_impact_types", "liabilities", ("負債", "有利子負債", "借入金")),
    Rule("financial.equity.001", "financial_impact_types", "equity", ("純資産", "自己資本", "株主資本")),
    Rule("financial.capex.001", "financial_impact_types", "capex", ("設備投資額", "設備投資", "capex")),
    Rule("financial.dividend.001", "financial_impact_types", "dividend", ("配当金", "年間配当", "配当予想")),
    Rule("financial.guidance.001", "financial_impact_types", "guidance", ("業績予想", "通期予想", "ガイダンス")),
)

ALL_RULES = DOCUMENT_TYPE_RULES + TOPIC_RULES + BUSINESS_EVENT_RULES + FINANCIAL_IMPACT_RULES

POSITIVE_KEYWORDS = ("増加", "増益", "上方修正", "回復", "改善", "拡大", "好調", "上昇効果")
NEGATIVE_KEYWORDS = ("減少", "減益", "下方修正", "低迷", "悪化", "損失", "減損", "供給制約", "操業停止")
NEUTRAL_KEYWORDS = ("影響は軽微", "影響は限定的", "業績への影響はありません", "影響なし")
FORECAST_KEYWORDS = ("予想", "見通し", "計画", "予定", "見込み", "将来")
ACTUAL_KEYWORDS = ("実績", "当期", "累計", "計上", "となりました", "実施しました")
IMMEDIATE_KEYWORDS = ("直ちに", "即時", "本日", "現時点")
CURRENT_PERIOD_KEYWORDS = ("当期", "今期", "当四半期", "通期", "本年度")
NEXT_PERIOD_KEYWORDS = ("来期", "次期", "翌期", "次年度")
MEDIUM_TERM_KEYWORDS = ("中期", "中長期", "3か年", "5か年", "将来")


# -----------------------------
# 3) データ構造
# -----------------------------
@dataclass
class BatchConfig:
    metadata_root: Path
    preprocessed_root: Path
    output_root: Path
    start_date: str = ""
    end_date: str = ""
    max_documents: Optional[int] = None


@dataclass
class PreprocessedDoc:
    document_id: str
    document_dir: Path
    metadata: Dict[str, Any]
    processing_report: Dict[str, Any]


@dataclass
class PreprocessedIndex:
    by_document_id: Dict[str, List[PreprocessedDoc]] = field(default_factory=lambda: defaultdict(list))
    by_source_id: Dict[str, List[PreprocessedDoc]] = field(default_factory=lambda: defaultdict(list))
    by_compound_key: Dict[str, List[PreprocessedDoc]] = field(default_factory=lambda: defaultdict(list))


@dataclass
class SourceItem:
    source_type: str
    source_id: str
    page_number: int
    order: int
    kind: str
    text: str
    normalized_text: str
    quality_score: float


@dataclass
class RuleMatch:
    rule: Rule
    score: int
    title_hit: bool
    heading_items: List[SourceItem]
    body_items: List[SourceItem]
    table_items: List[SourceItem]
    keyword_hits: List[str]
    negative_hit: bool

    @property
    def source_items(self) -> List[SourceItem]:
        return self.heading_items + self.body_items + self.table_items


# -----------------------------
# 4) 共通ユーティリティ
# -----------------------------
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


def _normalize_for_match(value: Any) -> str:
    text = _normalize_text(value).lower()
    return re.sub(r"[\s・･/／（）()「」『』【】\[\]［］:：,，。.!！?？\-―ー]+", "", text)


def _normalize_title_key(value: Any) -> str:
    return _normalize_for_match(value)


def _to_yyyymmdd(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{8}", text):
        datetime.strptime(text, "%Y%m%d")
        return text
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return datetime.strptime(text, "%Y-%m-%d").strftime("%Y%m%d")
    raise ValueError(f"invalid date: {value}")


def _date_range_inclusive(start_date: str, end_date: str) -> List[str]:
    start = datetime.strptime(_to_yyyymmdd(start_date), "%Y%m%d").date()
    end = datetime.strptime(_to_yyyymmdd(end_date), "%Y%m%d").date()
    if end < start:
        raise ValueError("END_DATE must be greater than or equal to START_DATE")
    days: List[str] = []
    current = start
    while current <= end:
        days.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return days


def _first_non_empty(row: Mapping[str, Any], names: Sequence[str], default: Any = "") -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return value
    return default


def _to_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _json_array(value: Sequence[Any]) -> str:
    return json.dumps(list(value), ensure_ascii=False, separators=(",", ":"))


def _load_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding=OUTPUT_ENCODING) as file:
            return json.load(file)
    except FileNotFoundError:
        return default


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding=OUTPUT_ENCODING) as file:
        for line_number, line in enumerate(file, 1):
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid_json:{path.name}:line={line_number}:{exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"invalid_json_object:{path.name}:line={line_number}")
            rows.append(value)
    return rows


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=OUTPUT_ENCODING) as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding=CSV_ENCODING, newline="") as file:
        return [{str(k): str(v or "") for k, v in row.items()} for row in csv.DictReader(file)]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=CSV_ENCODING, newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _source_id(row: Mapping[str, Any], row_number: int = 0) -> str:
    value = _first_non_empty(row, ["source_id", "disclosure_number", "document_url"])
    return str(value or f"row_{row_number}").strip()


def _issuer_code(row: Mapping[str, Any]) -> str:
    return str(_first_non_empty(row, ["code", "issuer_code"])).strip()


def _issuer_name(row: Mapping[str, Any]) -> str:
    return str(_first_non_empty(row, ["company_name", "issuer_name"])).strip()


def _metadata_csv_for_day(root: Path, day: str) -> Path:
    return root / f"tdnet_metadata_{day}.csv"


def _discover_available_days(metadata_root: Path) -> List[str]:
    if not metadata_root.exists():
        return []
    pattern = re.compile(r"^tdnet_metadata_(\d{8})\.csv$")
    return sorted({match.group(1) for path in metadata_root.iterdir() if (match := pattern.match(path.name))})


def _make_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = hashlib.sha1(f"{timestamp}-{time.time_ns()}".encode("utf-8")).hexdigest()[:8]
    return f"run_{timestamp}_{suffix}"


# -----------------------------
# 5) 前処理文書indexと突合
# -----------------------------
def _parse_front_matter(path: Path) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    if not path.exists():
        return metadata
    with path.open("r", encoding=OUTPUT_ENCODING) as file:
        in_header = False
        for index, line in enumerate(file):
            stripped = line.strip()
            if index == 0 and stripped == "---":
                in_header = True
                continue
            if in_header and stripped == "---":
                break
            if not in_header:
                break
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata


def _load_preprocessed_identity(document_dir: Path) -> Dict[str, Any]:
    front_matter = _parse_front_matter(document_dir / "normalized.md")
    package = _load_json(document_dir / "evidence_package.json", default={}) or {}
    package_metadata = package.get("document_metadata", {}) if isinstance(package, dict) else {}
    metadata = dict(package_metadata) if isinstance(package_metadata, dict) else {}
    metadata.update({key: value for key, value in front_matter.items() if value != ""})
    return metadata


def _compound_key(disclosure_date: Any, issuer_code: Any, title: Any) -> str:
    return f"{_to_yyyymmdd(disclosure_date)}|{str(issuer_code).strip()}|{_normalize_title_key(title)}"


def _build_preprocessed_index(day: str, root: Path) -> PreprocessedIndex:
    index = PreprocessedIndex()
    documents_root = root / day / "documents"
    if not documents_root.exists():
        return index

    for document_dir in sorted(path for path in documents_root.iterdir() if path.is_dir()):
        metadata = _load_preprocessed_identity(document_dir)
        report = _load_json(document_dir / "processing_report.json", default={}) or {}
        document_id = str(metadata.get("document_id") or report.get("document_id") or document_dir.name).strip()
        disclosure_date = str(metadata.get("disclosure_date", "")).strip()
        code = str(metadata.get("issuer_code", "")).strip()
        title = str(metadata.get("title", "")).strip()
        if not document_id or not disclosure_date or not code or not title:
            continue
        try:
            if _to_yyyymmdd(disclosure_date) != day:
                continue
        except ValueError:
            continue

        preprocessed = PreprocessedDoc(
            document_id=document_id,
            document_dir=document_dir,
            metadata=metadata,
            processing_report=report if isinstance(report, dict) else {},
        )
        index.by_document_id[document_id].append(preprocessed)
        source_id = str(metadata.get("source_id", "")).strip()
        if source_id:
            index.by_source_id[source_id].append(preprocessed)
        index.by_compound_key[_compound_key(disclosure_date, code, title)].append(preprocessed)
    return index


def _resolve_unique(candidates: Sequence[PreprocessedDoc]) -> Tuple[Optional[PreprocessedDoc], Optional[str]]:
    unique = {candidate.document_id: candidate for candidate in candidates}
    if not unique:
        return None, None
    if len(unique) > 1:
        return None, "ambiguous_preprocessed_document"
    return next(iter(unique.values())), None


def _resolve_preprocessed_doc(
    row: Mapping[str, Any],
    row_number: int,
    index: PreprocessedIndex,
) -> Tuple[Optional[PreprocessedDoc], Optional[str]]:
    direct_document_id = str(row.get("document_id", "") or "").strip()
    if direct_document_id:
        resolved, error = _resolve_unique(index.by_document_id.get(direct_document_id, []))
        if resolved or error:
            return resolved, error

    source_id = _source_id(row, row_number)
    if source_id:
        resolved, error = _resolve_unique(index.by_source_id.get(source_id, []))
        if resolved or error:
            return resolved, error

    disclosure_date = str(row.get("disclosure_date", "") or "").strip()
    code = _issuer_code(row)
    title = str(row.get("title", "") or "").strip()
    if disclosure_date and code and title:
        try:
            key = _compound_key(disclosure_date, code, title)
        except ValueError:
            return None, "invalid_disclosure_date"
        resolved, error = _resolve_unique(index.by_compound_key.get(key, []))
        if resolved or error:
            return resolved, error
    return None, "preprocessed_document_not_found"


# -----------------------------
# 6) 入力検証とcorpus
# -----------------------------
def _validate_metadata_columns(rows: Sequence[Mapping[str, Any]]) -> List[str]:
    if not rows:
        return []
    columns = set(rows[0].keys())
    errors: List[str] = []
    required_groups = (
        ("disclosure_date",),
        ("code", "issuer_code"),
        ("company_name", "issuer_name"),
        ("title",),
        ("document_url",),
    )
    for alternatives in required_groups:
        if not any(name in columns for name in alternatives):
            errors.append("missing_metadata_column:" + "|".join(alternatives))
    return errors


def _validate_document_identity(row: Mapping[str, Any], preprocessed: PreprocessedDoc) -> List[str]:
    errors: List[str] = []
    metadata = preprocessed.metadata
    if preprocessed.document_id != str(metadata.get("document_id", preprocessed.document_id)).strip():
        errors.append("document_identity_mismatch:document_id")
    if _issuer_code(row) != str(metadata.get("issuer_code", "")).strip():
        errors.append("document_identity_mismatch:issuer_code")
    if _normalize_title_key(row.get("title", "")) != _normalize_title_key(metadata.get("title", "")):
        errors.append("document_identity_mismatch:title")
    try:
        if _to_yyyymmdd(row.get("disclosure_date", "")) != _to_yyyymmdd(metadata.get("disclosure_date", "")):
            errors.append("document_identity_mismatch:disclosure_date")
    except ValueError:
        errors.append("document_identity_mismatch:disclosure_date")
    return errors


def _load_document_sources(preprocessed: PreprocessedDoc) -> Tuple[List[SourceItem], List[str]]:
    document_dir = preprocessed.document_dir
    blocks_path = document_dir / "document_blocks.jsonl"
    report_path = document_dir / "processing_report.json"
    normalized_path = document_dir / "normalized.md"
    package_path = document_dir / "evidence_package.json"
    missing: List[str] = []
    if not blocks_path.exists():
        missing.append("document_blocks.jsonl")
    if not report_path.exists():
        missing.append("processing_report.json")
    if not normalized_path.exists() and not package_path.exists():
        missing.append("normalized.md|evidence_package.json")
    if missing:
        raise ValueError("missing_required_artifact:" + ",".join(missing))

    report = preprocessed.processing_report
    processing_status = str(report.get("processing_status", "")).strip()
    if processing_status not in {"success", "success_with_warnings"}:
        raise ValueError("preprocessing_failed")

    block_rows = _load_jsonl(blocks_path)
    if not any(_normalize_text(row.get("text", "")) for row in block_rows):
        raise ValueError("empty_document_blocks")

    warnings: List[str] = []
    if processing_status == "success_with_warnings":
        warnings.append("preprocessing_success_with_warnings")
    table_rows: List[Dict[str, Any]] = []
    tables_path = document_dir / "document_tables.jsonl"
    if tables_path.exists():
        table_rows = _load_jsonl(tables_path)
    else:
        warnings.append("missing_optional_tables")

    items: List[SourceItem] = []
    for row in block_rows:
        document_id = str(row.get("document_id", "") or "").strip()
        if document_id != preprocessed.document_id:
            raise ValueError("document_identity_mismatch:block_document_id")
        text = _normalize_text(row.get("text", ""))
        if not text:
            continue
        kind = str(row.get("block_type", "unknown") or "unknown").strip()
        items.append(
            SourceItem(
                source_type="block",
                source_id=str(row.get("block_id", "") or "").strip(),
                page_number=_safe_int(row.get("page_number"), 1),
                order=_safe_int(row.get("block_order"), 1),
                kind=kind,
                text=text,
                normalized_text=_normalize_for_match(text),
                quality_score=max(0.0, min(1.0, _safe_float(row.get("quality_score"), 0.5))),
            )
        )

    for row in table_rows:
        document_id = str(row.get("document_id", "") or "").strip()
        if document_id != preprocessed.document_id:
            raise ValueError("document_identity_mismatch:table_document_id")
        text = _normalize_text(row.get("markdown_table", ""))
        if not text:
            continue
        items.append(
            SourceItem(
                source_type="table",
                source_id=str(row.get("table_id", "") or "").strip(),
                page_number=_safe_int(row.get("page_number"), 1),
                order=_safe_int(row.get("table_order"), 1),
                kind="table",
                text=text,
                normalized_text=_normalize_for_match(text),
                quality_score=max(0.0, min(1.0, _safe_float(row.get("quality_score"), 0.5))),
            )
        )
    return items, warnings


HEADING_TYPES = {"document_title", "page_title", "slide_title", "section_heading", "heading"}
IGNORED_TYPES = {"header", "footer"}


def _evaluate_rule(rule: Rule, title: str, items: Sequence[SourceItem], text_quality: str) -> RuleMatch:
    title_normalized = _normalize_for_match(title)
    keyword_pairs = [(keyword, _normalize_for_match(keyword)) for keyword in rule.keywords]
    title_hit = any(normalized and normalized in title_normalized for _, normalized in keyword_pairs)
    heading_items: List[SourceItem] = []
    body_items: List[SourceItem] = []
    table_items: List[SourceItem] = []
    keyword_hits: set[str] = set()

    for item in items:
        if item.kind in IGNORED_TYPES:
            continue
        hits = [keyword for keyword, normalized in keyword_pairs if normalized and normalized in item.normalized_text]
        if not hits:
            continue
        keyword_hits.update(hits)
        if item.source_type == "table":
            table_items.append(item)
        elif item.kind in HEADING_TYPES:
            heading_items.append(item)
        else:
            body_items.append(item)

    if title_hit:
        keyword_hits.update(keyword for keyword, normalized in keyword_pairs if normalized and normalized in title_normalized)

    all_normalized = "\n".join([title_normalized] + [item.normalized_text for item in items])
    negative_hit = any(_normalize_for_match(keyword) in all_normalized for keyword in rule.negative_keywords)
    score = 0
    if title_hit:
        score += 4
    if heading_items:
        score += 3
    if table_items:
        score += 2
    if body_items:
        score += 1
    distinct_sources = len({item.source_id for item in heading_items + body_items + table_items if item.source_id})
    score += min(2, max(0, distinct_sources - 1))
    if text_quality == "high" and (heading_items or body_items or table_items):
        score += 1
    if negative_hit:
        score -= 2
    return RuleMatch(
        rule=rule,
        score=max(0, score),
        title_hit=title_hit,
        heading_items=heading_items,
        body_items=body_items,
        table_items=table_items,
        keyword_hits=sorted(keyword_hits),
        negative_hit=negative_hit,
    )


def _evaluate_rules(
    rules: Sequence[Rule],
    title: str,
    items: Sequence[SourceItem],
    text_quality: str,
) -> List[RuleMatch]:
    return [
        match
        for rule in rules
        if (match := _evaluate_rule(rule, title, items, text_quality)).score > 0
    ]


def _confidence_from_score(score: int, text_quality: str, ambiguous: bool) -> float:
    if score >= 9:
        confidence = 0.90
    elif score >= 7:
        confidence = 0.80
    elif score >= 5:
        confidence = 0.68
    elif score >= 3:
        confidence = 0.55
    elif score > 0:
        confidence = 0.42
    else:
        confidence = 0.20
    if text_quality == "low":
        confidence = min(confidence, 0.45)
    elif text_quality == "medium":
        confidence = min(confidence, 0.79)
    if ambiguous:
        confidence = min(confidence, 0.59)
    return round(confidence, 2)


def _select_document_type(matches: Sequence[RuleMatch]) -> Tuple[str, List[Dict[str, Any]], bool]:
    ordered = sorted(matches, key=lambda match: (-match.score, match.rule.priority, match.rule.target_value))
    candidates = [
        {
            "value": match.rule.target_value,
            "score": match.score,
            "rule_id": match.rule.rule_id,
        }
        for match in ordered
    ]
    if not ordered:
        return "other", [], False
    top = ordered[0]
    ambiguous = any(
        match.score == top.score
        and match.rule.priority == top.rule.priority
        and match.rule.target_value != top.rule.target_value
        for match in ordered[1:]
    )
    return ("other" if ambiguous else top.rule.target_value), candidates, ambiguous


def _matched_values(matches: Sequence[RuleMatch]) -> List[str]:
    ordered = sorted(matches, key=lambda match: (-match.score, match.rule.priority, match.rule.target_value))
    return list(dict.fromkeys(match.rule.target_value for match in ordered))


def _classify_direction(all_text: str) -> str:
    normalized = _normalize_for_match(all_text)
    if any(_normalize_for_match(keyword) in normalized for keyword in NEUTRAL_KEYWORDS):
        return "neutral"
    positive = any(_normalize_for_match(keyword) in normalized for keyword in POSITIVE_KEYWORDS)
    negative = any(_normalize_for_match(keyword) in normalized for keyword in NEGATIVE_KEYWORDS)
    if positive and negative:
        return "mixed"
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "unclear"


def _classify_actual_or_forecast(all_text: str, has_impacts: bool) -> str:
    if not has_impacts:
        return "not_applicable"
    normalized = _normalize_for_match(all_text)
    forecast = any(_normalize_for_match(keyword) in normalized for keyword in FORECAST_KEYWORDS)
    actual = any(_normalize_for_match(keyword) in normalized for keyword in ACTUAL_KEYWORDS)
    if forecast and actual:
        return "both"
    if forecast:
        return "forecast"
    if actual:
        return "actual"
    return "unclear"


def _classify_time_horizon(all_text: str, has_impacts: bool) -> str:
    if not has_impacts:
        return "not_applicable"
    normalized = _normalize_for_match(all_text)
    matches: List[str] = []
    if any(_normalize_for_match(keyword) in normalized for keyword in IMMEDIATE_KEYWORDS):
        matches.append("immediate")
    if any(_normalize_for_match(keyword) in normalized for keyword in CURRENT_PERIOD_KEYWORDS):
        matches.append("current_period")
    if any(_normalize_for_match(keyword) in normalized for keyword in NEXT_PERIOD_KEYWORDS):
        matches.append("next_period")
    if any(_normalize_for_match(keyword) in normalized for keyword in MEDIUM_TERM_KEYWORDS):
        matches.append("medium_term")
    if len(set(matches)) > 1:
        return "multiple"
    return matches[0] if matches else "unclear"


QUANTITATIVE_PATTERN = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:%|％|円|億円|百万円|千円|株|件|台|トン|人|倍|bps?)",
    re.IGNORECASE,
)


def _has_quantitative_data(all_text: str) -> bool:
    return bool(QUANTITATIVE_PATTERN.search(unicodedata.normalize("NFKC", all_text)))


# -----------------------------
# 7) 根拠生成
# -----------------------------
def _context_for_block(center: SourceItem, items: Sequence[SourceItem]) -> List[SourceItem]:
    if center.source_type != "block":
        return [center]
    page_blocks = sorted(
        [
            item
            for item in items
            if item.source_type == "block"
            and item.page_number == center.page_number
            and item.kind not in IGNORED_TYPES
        ],
        key=lambda item: item.order,
    )
    by_order = {item.order: item for item in page_blocks}
    if center.kind in HEADING_TYPES:
        orders = [center.order, center.order + 1, center.order + 2]
    else:
        orders = [center.order - 1, center.order, center.order + 1]
    return [by_order[order] for order in orders if order in by_order]


def _build_evidence(
    document_id: str,
    matches: Sequence[RuleMatch],
    items: Sequence[SourceItem],
) -> List[Dict[str, Any]]:
    by_center: Dict[str, Dict[str, Any]] = {}
    for match in matches:
        for center in match.source_items:
            if not center.source_id:
                continue
            evidence = by_center.setdefault(
                center.source_id,
                {
                    "center": center,
                    "rule_ids": set(),
                    "keyword_hits": set(),
                },
            )
            evidence["rule_ids"].add(match.rule.rule_id)
            evidence["keyword_hits"].update(match.keyword_hits)

    ranked = sorted(
        by_center.values(),
        key=lambda value: (
            -float(value["center"].quality_score),
            0 if value["center"].kind in HEADING_TYPES else 1,
            value["center"].page_number,
            value["center"].order,
        ),
    )[:MAX_DETAIL_EVIDENCE]

    evidence_rows: List[Dict[str, Any]] = []
    for index, value in enumerate(ranked, 1):
        center: SourceItem = value["center"]
        context = _context_for_block(center, items)
        source_ids = list(dict.fromkeys(item.source_id for item in context if item.source_id))
        page_numbers = sorted({item.page_number for item in context})
        text = "\n\n".join(item.text for item in context).strip()
        if len(text) > MAX_EVIDENCE_CHARS:
            text = text[:MAX_EVIDENCE_CHARS]
        source_types = {item.source_type for item in context}
        source_type = next(iter(source_types)) if len(source_types) == 1 else "mixed"
        evidence_rows.append(
            {
                "evidence_id": f"{document_id}_gev{index:03d}",
                "source_type": source_type,
                "source_ids": source_ids,
                "page_numbers": page_numbers,
                "matched_rule_ids": sorted(value["rule_ids"]),
                "keyword_hits": sorted(value["keyword_hits"]),
                "text": text,
                "quality_score": round(center.quality_score, 4),
            }
        )
    return evidence_rows


# -----------------------------
# 8) 分類、routing、validation
# -----------------------------
def _classification_reason(
    document_type: str,
    candidates: Sequence[Mapping[str, Any]],
    confidence: float,
    evidence_count: int,
    ambiguous: bool,
) -> str:
    if ambiguous:
        return "同一score・同一priorityの開示種別候補が競合したため判定保留"
    if document_type == "other":
        return "開示種別ルールに十分な一致なし"
    top = candidates[0] if candidates else {}
    return (
        f"{top.get('rule_id', 'unknown_rule')} が最上位"
        f"(score={top.get('score', 0)}, confidence={confidence:.2f}, evidence={evidence_count})"
    )


def _route(
    document_type: str,
    confidence: float,
    evidence: Sequence[Mapping[str, Any]],
    business_events: Sequence[str],
    financial_impacts: Sequence[str],
    text_quality: str,
    ambiguous: bool,
    warnings: Sequence[str],
) -> Dict[str, Any]:
    has_impact = bool(business_events or financial_impacts)
    has_evidence = bool(evidence)
    review_reasons: List[str] = []
    if text_quality == "low":
        review_reasons.append("low_text_extraction_quality")
    if ambiguous:
        review_reasons.append("ambiguous_document_type")
    if "missing_optional_tables" in warnings:
        review_reasons.append("missing_optional_tables")

    if text_quality == "low" or ambiguous:
        stage = "needs_review"
    elif confidence >= 0.60 and has_evidence:
        stage = "body_supported"
    elif confidence >= 0.40:
        stage = "body_weak"
    else:
        stage = "body_unclassified"

    if document_type in LOW_VALUE_DOCUMENT_TYPES and not business_events:
        priority = "skip"
    elif (
        document_type in HIGH_VALUE_DOCUMENT_TYPES
        and confidence >= 0.75
        and has_evidence
        and has_impact
        and text_quality != "low"
        and not ambiguous
    ):
        priority = "high"
    elif confidence >= 0.55 and has_evidence and has_impact and text_quality != "low" and not ambiguous:
        priority = "medium"
    elif document_type == "other" and confidence < 0.40:
        priority = "skip"
    else:
        priority = "low"

    needs_extraction = bool(
        priority in {"high", "medium"}
        and has_evidence
        and has_impact
        and text_quality != "low"
        and not ambiguous
    )
    return {
        "downstream_priority": priority,
        "needs_structured_extraction": needs_extraction,
        "candidate_stage": stage,
        "review_hint": ";".join(review_reasons) if review_reasons else None,
    }


def _validate_detail(payload: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    classification = payload.get("classification", {})
    routing = payload.get("routing", {})
    quality = payload.get("quality", {})
    evidence = payload.get("evidence", [])

    document_type = classification.get("document_type")
    if document_type not in DOCUMENT_TYPES:
        errors.append(f"invalid_document_type:{document_type}")
    for field_name, allowed in (
        ("topic_tags", TOPIC_TAGS),
        ("business_event_types", BUSINESS_EVENT_TYPES),
        ("financial_impact_types", FINANCIAL_IMPACT_TYPES),
    ):
        invalid = [value for value in classification.get(field_name, []) if value not in allowed]
        if invalid:
            errors.append(f"invalid_{field_name}:{invalid}")
    if classification.get("impact_direction") not in IMPACT_DIRECTIONS:
        errors.append("invalid_impact_direction")
    if classification.get("actual_or_forecast") not in ACTUAL_OR_FORECAST_VALUES:
        errors.append("invalid_actual_or_forecast")
    if classification.get("time_horizon") not in TIME_HORIZONS:
        errors.append("invalid_time_horizon")
    confidence = _safe_float(classification.get("body_confidence"), -1.0)
    if not 0.0 <= confidence <= 1.0:
        errors.append("body_confidence_out_of_range")

    priority = routing.get("downstream_priority")
    stage = routing.get("candidate_stage")
    needs_extraction = bool(routing.get("needs_structured_extraction"))
    if priority not in DOWNSTREAM_PRIORITIES:
        errors.append("invalid_downstream_priority")
    if stage not in CANDIDATE_STAGES:
        errors.append("invalid_candidate_stage")
    if priority == "high" and (confidence < 0.75 or not evidence):
        errors.append("high_priority_requires_confidence_and_evidence")
    if needs_extraction:
        if priority not in {"high", "medium"}:
            errors.append("structured_extraction_requires_priority")
        if not evidence:
            errors.append("structured_extraction_requires_evidence")
        if quality.get("text_extraction_quality") == "low":
            errors.append("structured_extraction_forbidden_for_low_quality")
        if not (
            classification.get("business_event_types")
            or classification.get("financial_impact_types")
        ):
            errors.append("structured_extraction_requires_impact")
    if stage == "body_supported" and (confidence < 0.60 or not evidence):
        errors.append("body_supported_requires_confidence_and_evidence")
    if quality.get("text_extraction_quality") == "low":
        if stage != "needs_review":
            errors.append("low_quality_requires_review")
        if needs_extraction:
            errors.append("low_quality_forbids_structured_extraction")

    evidence_ids = [str(item.get("evidence_id", "")) for item in evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append("duplicate_evidence_id")
    if not payload.get("schema_version") or not payload.get("enrichment_version"):
        errors.append("missing_version")
    return errors


def _classify_document(
    *,
    document_id: str,
    row: Mapping[str, Any],
    items: Sequence[SourceItem],
    text_quality: str,
    warnings: Sequence[str],
) -> Dict[str, Any]:
    title = str(row.get("title", "") or "")
    document_matches = _evaluate_rules(DOCUMENT_TYPE_RULES, title, items, text_quality)
    topic_matches = _evaluate_rules(TOPIC_RULES, title, items, text_quality)
    business_matches = _evaluate_rules(BUSINESS_EVENT_RULES, title, items, text_quality)
    financial_matches = _evaluate_rules(FINANCIAL_IMPACT_RULES, title, items, text_quality)
    all_matches = document_matches + topic_matches + business_matches + financial_matches

    document_type, document_candidates, ambiguous = _select_document_type(document_matches)
    top_score = int(document_candidates[0]["score"]) if document_candidates else 0
    confidence = _confidence_from_score(top_score, text_quality, ambiguous)
    evidence = _build_evidence(document_id, all_matches, items)
    topic_tags = _matched_values(topic_matches) or ["other"]
    business_events = _matched_values(business_matches)
    financial_impacts = _matched_values(financial_matches)
    all_text = "\n".join([title] + [item.text for item in items if item.kind not in IGNORED_TYPES])
    has_impacts = bool(business_events or financial_impacts)

    classification = {
        "document_type": document_type,
        "document_type_candidates": document_candidates,
        "topic_tags": topic_tags,
        "business_event_types": business_events,
        "financial_impact_types": financial_impacts,
        "impact_direction": _classify_direction(all_text),
        "actual_or_forecast": _classify_actual_or_forecast(all_text, has_impacts),
        "time_horizon": _classify_time_horizon(all_text, has_impacts),
        "quantitative_data_present": _has_quantitative_data(all_text),
        "body_confidence": confidence,
        "classification_reason": _classification_reason(
            document_type,
            document_candidates,
            confidence,
            len(evidence),
            ambiguous,
        ),
    }
    routing = _route(
        document_type,
        confidence,
        evidence,
        business_events,
        financial_impacts,
        text_quality,
        ambiguous,
        warnings,
    )
    signals = {
        "matched_rule_ids": sorted({match.rule.rule_id for match in all_matches}),
        "title_rule_ids": sorted({match.rule.rule_id for match in all_matches if match.title_hit}),
        "negative_rule_ids": sorted({match.rule.rule_id for match in all_matches if match.negative_hit}),
        "rule_scores": {
            match.rule.rule_id: match.score
            for match in sorted(all_matches, key=lambda item: item.rule.rule_id)
        },
        "source_hit_counts": {
            "heading": sum(len(match.heading_items) for match in all_matches),
            "body": sum(len(match.body_items) for match in all_matches),
            "table": sum(len(match.table_items) for match in all_matches),
        },
        "ambiguous_document_type": ambiguous,
    }
    source_metadata = {
        "source_id": _source_id(row),
        "disclosure_date": str(row.get("disclosure_date", "") or ""),
        "disclosure_time": str(row.get("disclosure_time", "") or "") or None,
        "issuer_code": _issuer_code(row),
        "issuer_name": _issuer_name(row),
        "title": title,
        "document_url": str(row.get("document_url", "") or ""),
    }
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "enrichment_version": ENRICHMENT_VERSION,
        "enrichment_method": ENRICHMENT_METHOD,
        "document_id": document_id,
        "source_metadata": source_metadata,
        "classification": classification,
        "evidence": evidence,
        "signals": signals,
        "routing": routing,
        "quality": {
            "text_extraction_quality": text_quality,
            "warning_codes": sorted(set(warnings)),
        },
        "validation": {"status": "success", "errors": []},
        "generated_at_utc": _utc_now(),
    }
    validation_errors = _validate_detail(payload)
    status = "failed_validation" if validation_errors else (
        "needs_review" if routing["candidate_stage"] == "needs_review" else "success"
    )
    payload["validation"] = {"status": status, "errors": validation_errors}
    return payload


# -----------------------------
# 9) JSON正本からCSV projection
# -----------------------------
MAIN_COLUMNS = (
    "schema_version",
    "enrichment_version",
    "enrichment_method",
    "document_id",
    "source_id",
    "disclosure_date",
    "disclosure_time",
    "issuer_code",
    "issuer_name",
    "title",
    "document_url",
    "status",
    "document_type",
    "topic_tags",
    "business_event_types",
    "financial_impact_types",
    "impact_direction",
    "actual_or_forecast",
    "time_horizon",
    "quantitative_data_present",
    "body_confidence",
    "evidence_ids",
    "evidence_preview",
    "classification_reason",
    "text_extraction_quality",
    "downstream_priority",
    "needs_structured_extraction",
    "candidate_stage",
    "review_hint",
    "warning_codes",
    "validation_errors",
    "generated_at_utc",
)
SUMMARY_COLUMNS = (
    "run_id",
    "target_date",
    "source_id",
    "document_id",
    "status",
    "error_code",
    "error_message",
    "title",
    "output_path",
    "document_type",
    "downstream_priority",
    "needs_structured_extraction",
    "processing_duration_ms",
    "schema_version",
    "enrichment_version",
)
FAILED_COLUMNS = (
    "run_id",
    "target_date",
    "source_id",
    "document_id",
    "title",
    "error_code",
    "error_message",
    "retryable",
    "schema_version",
    "enrichment_version",
    "generated_at_utc",
)


def _project_main_row(payload: Mapping[str, Any]) -> Dict[str, Any]:
    source = payload["source_metadata"]
    classification = payload["classification"]
    routing = payload["routing"]
    quality = payload["quality"]
    validation = payload["validation"]
    evidence = payload["evidence"]
    evidence_ids = [item["evidence_id"] for item in evidence[:MAX_CSV_EVIDENCE_IDS]]
    evidence_preview = (
        str(evidence[0].get("text", ""))[:MAX_EVIDENCE_PREVIEW_CHARS]
        if evidence
        else None
    )
    row = {
        "schema_version": payload["schema_version"],
        "enrichment_version": payload["enrichment_version"],
        "enrichment_method": payload["enrichment_method"],
        "document_id": payload["document_id"],
        "source_id": source["source_id"],
        "disclosure_date": source["disclosure_date"],
        "disclosure_time": source.get("disclosure_time"),
        "issuer_code": source["issuer_code"],
        "issuer_name": source["issuer_name"],
        "title": source["title"],
        "document_url": source["document_url"],
        "status": validation["status"],
        "document_type": classification["document_type"],
        "topic_tags": _json_array(classification["topic_tags"]),
        "business_event_types": _json_array(classification["business_event_types"]),
        "financial_impact_types": _json_array(classification["financial_impact_types"]),
        "impact_direction": classification["impact_direction"],
        "actual_or_forecast": classification["actual_or_forecast"],
        "time_horizon": classification["time_horizon"],
        "quantitative_data_present": classification["quantitative_data_present"],
        "body_confidence": classification["body_confidence"],
        "evidence_ids": _json_array(evidence_ids),
        "evidence_preview": evidence_preview,
        "classification_reason": classification["classification_reason"],
        "text_extraction_quality": quality["text_extraction_quality"],
        "downstream_priority": routing["downstream_priority"],
        "needs_structured_extraction": routing["needs_structured_extraction"],
        "candidate_stage": routing["candidate_stage"],
        "review_hint": routing.get("review_hint"),
        "warning_codes": _json_array(quality["warning_codes"]),
        "validation_errors": _json_array(validation["errors"]),
        "generated_at_utc": payload["generated_at_utc"],
    }
    _validate_projection(payload, row)
    return row


def _validate_projection(payload: Mapping[str, Any], row: Mapping[str, Any]) -> None:
    evidence = payload.get("evidence", [])
    detail_ids = {item.get("evidence_id") for item in evidence}
    csv_ids = set(json.loads(str(row.get("evidence_ids", "[]"))))
    if not csv_ids.issubset(detail_ids):
        raise ValueError("failed_validation:evidence_alignment")
    expected_preview = (
        str(evidence[0].get("text", ""))[:MAX_EVIDENCE_PREVIEW_CHARS]
        if evidence
        else None
    )
    if row.get("evidence_preview") != expected_preview:
        raise ValueError("failed_validation:evidence_preview_alignment")
    if len(str(row.get("evidence_preview") or "")) > MAX_EVIDENCE_PREVIEW_CHARS:
        raise ValueError("failed_validation:evidence_preview_length")
    if "document_type_candidates" in row:
        raise ValueError("failed_validation:detail_only_field_in_csv")


def _error_code(error: Exception | str) -> str:
    message = str(error)
    return message.split(":", 1)[0] if message else "unexpected_error"


def _is_retryable(error_code: str) -> bool:
    return error_code in {
        "preprocessed_document_not_found",
        "ambiguous_preprocessed_document",
        "missing_required_artifact",
        "preprocessing_failed",
        "unexpected_error",
    }


# -----------------------------
# 10) 文書処理とbatch
# -----------------------------
def _process_document(
    *,
    row: Mapping[str, Any],
    preprocessed: PreprocessedDoc,
    output_document_dir: Path,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    identity_errors = _validate_document_identity(row, preprocessed)
    if identity_errors:
        raise ValueError(identity_errors[0])
    items, warnings = _load_document_sources(preprocessed)
    text_quality = str(
        preprocessed.processing_report.get("document_text_extraction_quality", "low")
    ).strip()
    if text_quality not in TEXT_QUALITIES:
        warnings.append("invalid_text_extraction_quality")
        text_quality = "low"
    payload = _classify_document(
        document_id=preprocessed.document_id,
        row=row,
        items=items,
        text_quality=text_quality,
        warnings=warnings,
    )
    output_path = output_document_dir / "generic_body_metadata_enrichment.json"
    _save_json(output_path, payload)
    return payload, _project_main_row(payload)


def _summary_row(
    *,
    run_id: str,
    day: str,
    row: Mapping[str, Any],
    document_id: Optional[str],
    status: str,
    duration_ms: int,
    output_path: Optional[Path] = None,
    payload: Optional[Mapping[str, Any]] = None,
    error: Optional[Exception | str] = None,
) -> Dict[str, Any]:
    code = _error_code(error) if error else ""
    classification = payload.get("classification", {}) if payload else {}
    routing = payload.get("routing", {}) if payload else {}
    return {
        "run_id": run_id,
        "target_date": day,
        "source_id": _source_id(row),
        "document_id": document_id or "",
        "status": status,
        "error_code": code,
        "error_message": str(error or ""),
        "title": str(row.get("title", "") or ""),
        "output_path": str(output_path or ""),
        "document_type": classification.get("document_type", ""),
        "downstream_priority": routing.get("downstream_priority", ""),
        "needs_structured_extraction": bool(routing.get("needs_structured_extraction", False)),
        "processing_duration_ms": duration_ms,
        "schema_version": SCHEMA_VERSION,
        "enrichment_version": ENRICHMENT_VERSION,
    }


def _failed_row(
    *,
    run_id: str,
    day: str,
    row: Mapping[str, Any],
    document_id: Optional[str],
    error: Exception | str,
) -> Dict[str, Any]:
    code = _error_code(error)
    return {
        "run_id": run_id,
        "target_date": day,
        "source_id": _source_id(row),
        "document_id": document_id or "",
        "title": str(row.get("title", "") or ""),
        "error_code": code,
        "error_message": str(error),
        "retryable": _is_retryable(code),
        "schema_version": SCHEMA_VERSION,
        "enrichment_version": ENRICHMENT_VERSION,
        "generated_at_utc": _utc_now(),
    }


def _report(
    *,
    run_id: str,
    started_at: str,
    finished_at: str,
    input_count: int,
    matched_count: int,
    main_rows: Sequence[Mapping[str, Any]],
    summary_rows: Sequence[Mapping[str, Any]],
    failed_rows: Sequence[Mapping[str, Any]],
    output_paths: Mapping[str, str],
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    status_counts = Counter(str(row.get("status", "")) for row in summary_rows)
    runtime_failed_count = status_counts.get("failed", 0)
    error_counts = Counter(str(row.get("error_code", "")) for row in failed_rows if row.get("error_code"))
    report = {
        "run_id": run_id,
        "schema_version": SCHEMA_VERSION,
        "enrichment_version": ENRICHMENT_VERSION,
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "input_count": input_count,
        "matched_count": matched_count,
        "processed_count": len(main_rows),
        "success_count": status_counts.get("success", 0),
        "needs_review_count": status_counts.get("needs_review", 0),
        "failed_validation_count": status_counts.get("failed_validation", 0),
        "failed_count": runtime_failed_count,
        "document_type_counts": dict(Counter(str(row.get("document_type", "")) for row in main_rows)),
        "priority_counts": dict(Counter(str(row.get("downstream_priority", "")) for row in main_rows)),
        "text_quality_counts": dict(Counter(str(row.get("text_extraction_quality", "")) for row in main_rows)),
        "error_code_counts": dict(error_counts),
        "needs_structured_extraction_count": sum(
            1 for row in main_rows if bool(row.get("needs_structured_extraction"))
        ),
        "output_paths": dict(output_paths),
    }
    if target_date:
        report["target_date"] = target_date
    if input_count != len(main_rows) + runtime_failed_count:
        raise ValueError(
            "count_reconciliation_failed:"
            f"input={input_count},processed={len(main_rows)},failed={runtime_failed_count}"
        )
    if len(main_rows) != (
        status_counts.get("success", 0)
        + status_counts.get("needs_review", 0)
        + status_counts.get("failed_validation", 0)
    ):
        raise ValueError("status_count_reconciliation_failed")
    return report


def run_batch(config: BatchConfig) -> Dict[str, Any]:
    if not config.metadata_root.exists():
        raise FileNotFoundError(f"metadata root not found: {config.metadata_root}")
    if not config.preprocessed_root.exists():
        raise FileNotFoundError(f"preprocessed root not found: {config.preprocessed_root}")
    config.output_root.mkdir(parents=True, exist_ok=True)

    if config.start_date or config.end_date:
        if not (config.start_date and config.end_date):
            raise ValueError("Both start_date and end_date are required")
        target_days = _date_range_inclusive(config.start_date, config.end_date)
    else:
        target_days = _discover_available_days(config.metadata_root)
    if not target_days:
        raise RuntimeError("no daily metadata files found")

    run_id = _make_run_id()
    run_started = _utc_now()
    all_main: List[Dict[str, Any]] = []
    all_summary: List[Dict[str, Any]] = []
    all_failed: List[Dict[str, Any]] = []
    all_input_count = 0
    all_matched_count = 0
    remaining = config.max_documents if config.max_documents and config.max_documents > 0 else None

    for day in target_days:
        metadata_path = _metadata_csv_for_day(config.metadata_root, day)
        if not metadata_path.exists():
            print(f"[warn] metadata missing day={day}: {metadata_path}")
            continue
        rows = _read_csv(metadata_path)
        metadata_errors = _validate_metadata_columns(rows)
        if metadata_errors:
            raise ValueError(metadata_errors[0])
        day_rows: List[Dict[str, str]] = []
        for row in rows:
            try:
                if _to_yyyymmdd(row.get("disclosure_date", "")) == day:
                    day_rows.append(row)
                else:
                    raise ValueError("invalid_disclosure_date")
            except ValueError:
                day_rows.append(row)
        if remaining is not None:
            day_rows = day_rows[:remaining]
            remaining -= len(day_rows)
        if not day_rows:
            continue

        day_started = _utc_now()
        day_main: List[Dict[str, Any]] = []
        day_summary: List[Dict[str, Any]] = []
        day_failed: List[Dict[str, Any]] = []
        day_matched = 0
        index = _build_preprocessed_index(day, config.preprocessed_root)
        day_output = config.output_root / day

        for row_number, row in enumerate(day_rows, 1):
            started_ns = time.perf_counter_ns()
            preprocessed, resolve_error = _resolve_preprocessed_doc(row, row_number, index)
            if resolve_error or not preprocessed:
                error = resolve_error or "preprocessed_document_not_found"
                duration = int((time.perf_counter_ns() - started_ns) / 1_000_000)
                day_summary.append(
                    _summary_row(
                        run_id=run_id,
                        day=day,
                        row=row,
                        document_id=None,
                        status="failed",
                        duration_ms=duration,
                        error=error,
                    )
                )
                day_failed.append(
                    _failed_row(
                        run_id=run_id,
                        day=day,
                        row=row,
                        document_id=None,
                        error=error,
                    )
                )
                continue

            day_matched += 1
            output_document_dir = day_output / "documents" / preprocessed.document_id
            try:
                payload, main_row = _process_document(
                    row=row,
                    preprocessed=preprocessed,
                    output_document_dir=output_document_dir,
                )
                duration = int((time.perf_counter_ns() - started_ns) / 1_000_000)
                status = str(payload["validation"]["status"])
                output_path = output_document_dir / "generic_body_metadata_enrichment.json"
                day_main.append(main_row)
                day_summary.append(
                    _summary_row(
                        run_id=run_id,
                        day=day,
                        row=row,
                        document_id=preprocessed.document_id,
                        status=status,
                        duration_ms=duration,
                        output_path=output_path,
                        payload=payload,
                        error=(
                            "failed_validation:" + "|".join(payload["validation"]["errors"])
                            if status == "failed_validation"
                            else None
                        ),
                    )
                )
                if status == "failed_validation":
                    day_failed.append(
                        _failed_row(
                            run_id=run_id,
                            day=day,
                            row=row,
                            document_id=preprocessed.document_id,
                            error="failed_validation:" + "|".join(payload["validation"]["errors"]),
                        )
                    )
            except Exception as exc:
                duration = int((time.perf_counter_ns() - started_ns) / 1_000_000)
                day_summary.append(
                    _summary_row(
                        run_id=run_id,
                        day=day,
                        row=row,
                        document_id=preprocessed.document_id,
                        status="failed",
                        duration_ms=duration,
                        error=exc,
                    )
                )
                day_failed.append(
                    _failed_row(
                        run_id=run_id,
                        day=day,
                        row=row,
                        document_id=preprocessed.document_id,
                        error=exc,
                    )
                )

        day_main_path = day_output / "generic_body_enriched_disclosure_metadata.csv"
        day_summary_path = day_output / "enrichment_summary.csv"
        day_failed_path = day_output / "enrichment_failed.csv"
        day_report_path = day_output / "daily_enrichment_report.json"
        _write_csv(day_main_path, day_main, MAIN_COLUMNS)
        _write_csv(day_summary_path, day_summary, SUMMARY_COLUMNS)
        _write_csv(day_failed_path, day_failed, FAILED_COLUMNS)
        day_report = _report(
            run_id=run_id,
            started_at=day_started,
            finished_at=_utc_now(),
            input_count=len(day_rows),
            matched_count=day_matched,
            main_rows=day_main,
            summary_rows=day_summary,
            failed_rows=day_failed,
            output_paths={
                "main_csv": str(day_main_path),
                "summary_csv": str(day_summary_path),
                "failed_csv": str(day_failed_path),
                "report_json": str(day_report_path),
            },
            target_date=day,
        )
        _save_json(day_report_path, day_report)
        all_input_count += len(day_rows)
        all_matched_count += day_matched
        all_main.extend(day_main)
        all_summary.extend(day_summary)
        all_failed.extend(day_failed)
        print(
            f"[done] day={day} input={len(day_rows)} processed={len(day_main)} "
            f"runtime_failed={sum(1 for row in day_summary if row['status'] == 'failed')}"
        )
        if remaining is not None and remaining <= 0:
            break

    all_main_path = config.output_root / "generic_body_enriched_disclosure_metadata_all.csv"
    all_summary_path = config.output_root / "enrichment_summary_all.csv"
    all_failed_path = config.output_root / "enrichment_failed_all.csv"
    all_report_path = config.output_root / "enrichment_report_all.json"
    _write_csv(all_main_path, all_main, MAIN_COLUMNS)
    _write_csv(all_summary_path, all_summary, SUMMARY_COLUMNS)
    _write_csv(all_failed_path, all_failed, FAILED_COLUMNS)
    run_report = _report(
        run_id=run_id,
        started_at=run_started,
        finished_at=_utc_now(),
        input_count=all_input_count,
        matched_count=all_matched_count,
        main_rows=all_main,
        summary_rows=all_summary,
        failed_rows=all_failed,
        output_paths={
            "main_csv": str(all_main_path),
            "summary_csv": str(all_summary_path),
            "failed_csv": str(all_failed_path),
            "report_json": str(all_report_path),
        },
    )
    _save_json(all_report_path, run_report)
    print(
        f"[done] run={run_id} input={all_input_count} processed={len(all_main)} "
        f"failed={run_report['failed_count']}"
    )
    return run_report


# -----------------------------
# 11) 組み込みself-check
# -----------------------------
def _test_items(title: str, body: str, quality: float = 0.95) -> List[SourceItem]:
    return [
        SourceItem(
            source_type="block",
            source_id="doc_test_p001_b001",
            page_number=1,
            order=1,
            kind="document_title",
            text=title,
            normalized_text=_normalize_for_match(title),
            quality_score=quality,
        ),
        SourceItem(
            source_type="block",
            source_id="doc_test_p001_b002",
            page_number=1,
            order=2,
            kind="paragraph",
            text=body,
            normalized_text=_normalize_for_match(body),
            quality_score=quality,
        ),
    ]


def _test_classification(title: str, body: str, text_quality: str = "high") -> Dict[str, Any]:
    return _classify_document(
        document_id="doc_test",
        row={
            "disclosure_number": "test_source",
            "disclosure_date": "2026-07-16",
            "disclosure_time": "15:00",
            "code": "0000",
            "company_name": "テスト株式会社",
            "title": title,
            "document_url": "https://example.invalid/test.pdf",
        },
        items=_test_items(title, body),
        text_quality=text_quality,
        warnings=[],
    )


def run_self_checks() -> None:
    cases = [
        ("earnings_release", "2026年3月期 決算短信", "売上高100億円、営業利益10億円となりました"),
        ("earnings_presentation", "2026年3月期 決算説明資料", "決算説明会資料 売上高と営業利益の実績"),
        ("forecast_revision", "業績予想の修正に関するお知らせ", "需要低迷により通期売上高予想を100億円へ下方修正"),
        ("ma_restructuring", "子会社株式の取得に関するお知らせ", "株式取得により子会社化し、総資産が増加"),
        ("capex_fixed_assets", "新工場建設に関するお知らせ", "設備投資額100億円で生産能力増強を予定"),
        ("impairment", "減損損失の計上に関するお知らせ", "固定資産の減損損失20億円を当期純利益に計上"),
    ]
    for expected, title, body in cases:
        payload = _test_classification(title, body)
        actual = payload["classification"]["document_type"]
        assert actual == expected, (expected, actual, title)

    multi = _test_classification(
        "業績予想の修正に関するお知らせ",
        "原材料価格上昇と需要低迷により売上高と営業利益を下方修正。価格改定も実施予定。",
    )
    assert {"outlook", "costs", "demand_sales", "pricing"}.issubset(
        set(multi["classification"]["topic_tags"])
    )
    assert {"revenue", "operating_profit", "guidance"}.issubset(
        set(multi["classification"]["financial_impact_types"])
    )

    capex = _test_classification("新工場建設に関するお知らせ", "設備投資100億円で生産能力増強")
    assert "capacity_change" in capex["classification"]["business_event_types"]
    assert "capex" in capex["classification"]["financial_impact_types"]
    assert capex["classification"]["quantitative_data_present"] is True

    impairment = _test_classification("減損損失の計上", "減損損失10億円により当期純利益が減少")
    assert impairment["classification"]["impact_direction"] == "negative"

    dividend = _test_classification("剰余金の配当に関するお知らせ", "年間配当金を1株当たり20円とする")
    assert dividend["routing"]["downstream_priority"] == "skip"

    governance = _test_classification("代表取締役の異動に関するお知らせ", "代表取締役の人事異動")
    assert governance["routing"]["downstream_priority"] == "skip"

    cancellation = _test_classification("設備投資計画の中止に関するお知らせ", "新工場計画を中止します")
    assert cancellation["classification"]["impact_direction"] != "positive"

    mixed = _test_classification("業績に関するお知らせ", "販売数量増加で増益だが、原材料価格上昇で利益は減少")
    assert mixed["classification"]["impact_direction"] == "mixed"

    low_quality = _test_classification(
        "業績予想の修正に関するお知らせ",
        "売上高予想を下方修正",
        text_quality="low",
    )
    assert low_quality["routing"]["candidate_stage"] == "needs_review"
    assert low_quality["routing"]["needs_structured_extraction"] is False

    custom_rules = (
        Rule("tie.a", "document_type", "earnings_release", ("共通語",), priority=1),
        Rule("tie.b", "document_type", "forecast_revision", ("共通語",), priority=1),
    )
    tie_matches = _evaluate_rules(custom_rules, "共通語", _test_items("共通語", "共通語"), "high")
    tie_type, _, tie_ambiguous = _select_document_type(tie_matches)
    assert tie_type == "other" and tie_ambiguous is True

    no_evidence_route = _route(
        "forecast_revision",
        0.90,
        [],
        ["demand_change"],
        ["guidance"],
        "high",
        False,
        [],
    )
    assert no_evidence_route["needs_structured_extraction"] is False

    projection = _project_main_row(multi)
    assert "document_type_candidates" not in projection
    assert isinstance(json.loads(projection["topic_tags"]), list)
    assert len(str(projection["evidence_preview"] or "")) <= MAX_EVIDENCE_PREVIEW_CHARS

    invalid_payload = json.loads(json.dumps(multi, ensure_ascii=False))
    invalid_payload["routing"]["downstream_priority"] = "high"
    invalid_payload["classification"]["body_confidence"] = 0.20
    assert "high_priority_requires_confidence_and_evidence" in _validate_detail(invalid_payload)

    print("[self-check] all checks passed")


def run_fixture_smoke_test() -> None:
    with tempfile.TemporaryDirectory(prefix="generic_enrichment_") as temporary:
        root = Path(temporary)
        metadata_root = root / "data/original"
        preprocessed_root = root / "data/processed/tdnet_pdf_preprocessed"
        output_root = root / "data/processed/tdnet_generic_body_metadata_enriched"
        day = "20260716"
        document_id = "20260716_0000_abcdef12"
        document_dir = preprocessed_root / day / "documents" / document_id
        metadata_root.mkdir(parents=True)
        document_dir.mkdir(parents=True)

        _write_csv(
            metadata_root / f"tdnet_metadata_{day}.csv",
            [
                {
                    "disclosure_date": "2026-07-16",
                    "disclosure_time": "15:00",
                    "disclosure_number": "fixture_001",
                    "code": "0000",
                    "company_name": "テスト株式会社",
                    "title": "業績予想の修正に関するお知らせ",
                    "document_url": "https://example.invalid/fixture.pdf",
                }
            ],
            (
                "disclosure_date",
                "disclosure_time",
                "disclosure_number",
                "code",
                "company_name",
                "title",
                "document_url",
            ),
        )
        normalized = (
            "---\n"
            f"document_id: {document_id}\n"
            "source_id: fixture_001\n"
            "issuer_code: 0000\n"
            "issuer_name: テスト株式会社\n"
            "disclosure_date: 2026-07-16\n"
            "title: 業績予想の修正に関するお知らせ\n"
            "pdf_layout_type: doc_like\n"
            "page_count: 1\n"
            "---\n\n"
            "# 業績予想の修正に関するお知らせ\n"
        )
        (document_dir / "normalized.md").write_text(normalized, encoding=OUTPUT_ENCODING)
        blocks = _test_items(
            "業績予想の修正に関するお知らせ",
            "需要低迷により通期売上高予想を100億円へ下方修正",
        )
        with (document_dir / "document_blocks.jsonl").open("w", encoding=OUTPUT_ENCODING) as file:
            for item in blocks:
                file.write(
                    json.dumps(
                        {
                            "block_id": item.source_id.replace("doc_test", document_id),
                            "document_id": document_id,
                            "page_number": item.page_number,
                            "page_layout_type": "doc_like",
                            "block_order": item.order,
                            "block_type": item.kind,
                            "text": item.text,
                            "normalized_text": item.normalized_text,
                            "quality_score": item.quality_score,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        _save_json(
            document_dir / "processing_report.json",
            {
                "document_id": document_id,
                "processing_status": "success_with_warnings",
                "document_text_extraction_quality": "high",
                "page_count": 1,
                "block_count": 2,
                "table_count": 0,
            },
        )
        report = run_batch(
            BatchConfig(
                metadata_root=metadata_root,
                preprocessed_root=preprocessed_root,
                output_root=output_root,
                start_date=day,
                end_date=day,
                max_documents=1,
            )
        )
        assert report["input_count"] == 1
        assert report["processed_count"] == 1
        assert report["failed_count"] == 0
        main_rows = _read_csv(output_root / "generic_body_enriched_disclosure_metadata_all.csv")
        assert len(main_rows) == 1
        assert main_rows[0]["document_type"] == "forecast_revision"
        assert "document_type_candidates" not in main_rows[0]
        detail_path = output_root / day / "documents" / document_id / "generic_body_metadata_enrichment.json"
        detail = _load_json(detail_path)
        assert detail["classification"]["document_type_candidates"]
        assert "preprocessing_success_with_warnings" in detail["quality"]["warning_codes"]
        print("[fixture] smoke test passed")


# -----------------------------
# 12) entrypoint
# -----------------------------
def main() -> None:
    if RUN_SELF_CHECKS:
        run_self_checks()
    if SELF_CHECK_ONLY:
        return
    config = BatchConfig(
        metadata_root=Path(METADATA_ROOT_DIR),
        preprocessed_root=Path(PREPROCESSED_ROOT_DIR),
        output_root=Path(OUTPUT_ROOT_DIR),
        start_date=START_DATE,
        end_date=END_DATE,
        max_documents=MAX_DOCUMENTS,
    )
    run_batch(config)


if __name__ == "__main__":
    main()
