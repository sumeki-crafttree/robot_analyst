# -*- coding: utf-8 -*-

# ==========================================
# TDnet開示タイトル 不動産取引候補分類スクリプト（ペライチ）
# Colab 1セル貼り付け実行OK
#
# 機能:
#   - fetch_tdnet_metadata.py の出力CSVを入力
#   - 不動産取引候補フラグと3軸分類を付与
#   - confidence / 本文確認要否 / 理由を付与
# ==========================================

from __future__ import annotations

import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _ensure_dependency(module_name: str, pip_name: Optional[str] = None) -> None:
    try:
        __import__(module_name)
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name or module_name])


_ensure_dependency("pandas")
import pandas as pd


# -----------------------------
# 0) 設定（ここだけ編集すればOK）
# -----------------------------
ROOT_DIR = "/content/drive/MyDrive/git/prop_candidates/"
ORIGINAL_DIR = ROOT_DIR + "data/original/"
PROCESSED_DIR = ROOT_DIR + "data/processed/"
CLASSIFIED_DIR = PROCESSED_DIR + "tdnet_metadata_classified/"

START_DATE = ""  # YYYY-MM-DD or YYYYMMDD
END_DATE = ""  # YYYY-MM-DD or YYYYMMDD
OUTPUT_ENCODING = "utf-8-sig"


EXCLUSION_KEYWORDS: Sequence[str] = [
    "自己株式",
    "配当",
    "役員",
    "代表取締役",
    "定款",
    "株主総会",
    "監査法人",
    "月次",
    "決算説明会開催",
]

REAL_ESTATE_OVERRIDE_KEYWORDS: Sequence[str] = [
    "固定資産",
    "不動産",
    "土地",
    "建物",
    "譲渡",
    "売却",
    "取得",
    "信託受益権",
    "販売用不動産",
    "リースバック",
    "賃貸用不動産",
    "投資不動産",
    "物流センター",
    "工場用地",
]

ACTION_PRIORITY: Sequence[Tuple[str, Sequence[str]]] = [
    ("cancellation", ["中止", "解除", "撤回", "取りやめ"]),
    ("change_or_revision", ["日程変更", "一部変更", "変更", "経過"]),
    ("completion_or_closing", ["取得完了", "譲渡完了", "所有権移転", "引渡", "完了"]),
    ("reclassification", ["固定資産から販売用不動産", "販売用不動産への振替", "保有目的の変更", "振替"]),
    ("development", ["新物流センター", "物流センター", "工場用地", "新工場", "竣工", "建設", "開発", "新設"]),
    ("sale", ["譲渡益", "売却益", "譲渡", "売却", "処分"]),
    ("acquisition", ["取得価額", "取得", "購入"]),
    ("gain_loss_only", ["特別利益", "特別損失", "減損損失", "業績予想の修正"]),
]

SCHEME_PRIORITY: Sequence[Tuple[str, Sequence[str]]] = [
    ("sale_and_leaseback", ["セール・アンド・リースバック", "リースバック", "賃貸借契約締結", "継続使用"]),
    ("reclassification_to_inventory", ["固定資産から販売用不動産", "保有目的の変更", "販売用不動産への振替"]),
    ("trust_beneficiary_right_transaction", ["国内不動産信託受益権", "不動産信託受益権", "信託受益権"]),
    ("inventory_real_estate_transaction", ["販売用不動産", "棚卸資産"]),
    ("reit_asset_transaction", ["j-reit", "投資法人", "運用資産", "資産運用会社"]),
    ("direct_fixed_asset_transaction", ["固定資産の譲渡", "固定資産の取得", "固定資産", "土地", "建物", "構築物"]),
    ("indirect_possible_transaction", ["子会社の異動", "株式譲渡", "事業譲渡", "会社分割", "spc"]),
    ("lease_transaction", ["リース", "賃貸借"]),
]

ASSET_CONTEXT_PRIORITY: Sequence[Tuple[str, Sequence[str]]] = [
    ("real_estate_for_sale", ["販売用不動産", "棚卸資産"]),
    ("investment_or_leasing_property", ["賃貸用不動産", "投資不動産", "収益不動産"]),
    ("reit_operating_asset", ["j-reit", "投資法人", "運用資産"]),
    ("trust_underlying_real_estate", ["国内不動産信託受益権", "不動産信託受益権", "信託受益権"]),
    ("development_project", ["新工場", "新物流センター", "物流センター", "工場用地", "建設", "竣工", "開発"]),
    ("business_use_fixed_asset", ["本社", "工場", "物流センター", "配送センター", "店舗", "倉庫", "研究所", "事業所", "遊休資産"]),
    ("unknown_real_estate", ["固定資産", "資産の譲渡", "資産の取得", "特別利益", "特別損失"]),
]

STRONG_FALSE_NEEDS_READING: Sequence[str] = [
    "販売用不動産の売却",
    "販売用不動産の取得",
    "国内不動産信託受益権の取得",
    "信託受益権の譲渡",
    "固定資産から販売用不動産への保有目的変更",
]

TRUE_NEEDS_READING_KEYWORDS: Sequence[str] = [
    "固定資産の譲渡",
    "固定資産の取得",
    "資産の譲渡",
    "資産の取得",
    "特別利益",
    "特別損失",
    "業績予想の修正",
    "子会社の異動",
    "事業譲渡",
    "会社分割",
    "セール・アンド・リースバック",
    "リースバック",
]


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("　", " ").strip().lower()
    if not text:
        return ""

    replacements = {
        "セール&リースバック": "セール・アンド・リースバック",
        "セール＆リースバック": "セール・アンド・リースバック",
        "セールアンドリースバック": "セール・アンド・リースバック",
    }
    for src, dst in replacements.items():
        text = text.replace(src.lower(), dst.lower())

    # タイトル判定では空白/記号のゆれを吸収したいので連結する
    text = re.sub(r"[\s・･/／（）()「」『』【】\[\]]+", "", text)
    return text


def _contains_any(text: str, keywords: Sequence[str]) -> bool:
    return any(_normalize_text(k) in text for k in keywords if k)


def _matched_keywords(text: str, keywords: Sequence[str]) -> List[str]:
    return [k for k in keywords if _normalize_text(k) in text]


def _classify_by_priority(
    text: str,
    rules: Sequence[Tuple[str, Sequence[str]]],
    default_label: str,
) -> Tuple[str, List[str]]:
    for label, keywords in rules:
        hits = _matched_keywords(text, keywords)
        if hits:
            return label, hits
    return default_label, []


def _is_clear_non_real_estate(text: str) -> Tuple[bool, List[str]]:
    exclusion_hits = _matched_keywords(text, EXCLUSION_KEYWORDS)
    if not exclusion_hits:
        return False, []
    if _contains_any(text, REAL_ESTATE_OVERRIDE_KEYWORDS):
        return False, []
    return True, exclusion_hits


def _apply_consistency_rules(
    *,
    text: str,
    issuer_name_text: str,
    action: str,
    scheme: str,
    asset_context: str,
) -> Tuple[str, str, str, List[str]]:
    reasons: List[str] = []

    # 補正1: 固定資産 -> 販売用不動産 への保有目的変更
    if _contains_any(text, ["固定資産から販売用不動産", "販売用不動産への振替", "保有目的の変更"]):
        action = "reclassification"
        scheme = "reclassification_to_inventory"
        asset_context = "business_use_fixed_asset"
        reasons.append("固定資産から販売用不動産への保有目的変更キーワードを検知")

    # 補正2: セールアンドリースバック
    if _contains_any(text, ["セール・アンド・リースバック", "リースバック"]):
        scheme = "sale_and_leaseback"
        action = "sale"
        if asset_context not in ("business_use_fixed_asset", "unknown_real_estate"):
            asset_context = "unknown_real_estate"
        reasons.append("リースバック関連キーワードを検知")

    # 補正3: 信託受益権
    if _contains_any(text, ["国内不動産信託受益権", "不動産信託受益権", "信託受益権"]):
        scheme = "trust_beneficiary_right_transaction"
        asset_context = "trust_underlying_real_estate"
        if _contains_any(text, ["譲渡", "売却"]):
            action = "sale"
        elif _contains_any(text, ["取得", "購入"]):
            action = "acquisition"
        reasons.append("信託受益権キーワードを検知")

    # 補正4: 販売用不動産
    if _contains_any(text, ["販売用不動産"]):
        scheme = "inventory_real_estate_transaction"
        asset_context = "real_estate_for_sale"
        if _contains_any(text, ["譲渡", "売却"]):
            action = "sale"
        elif _contains_any(text, ["取得", "購入"]):
            action = "acquisition"
        reasons.append("販売用不動産キーワードを検知")

    # 補正5: J-REIT
    if _contains_any(text + issuer_name_text, ["投資法人", "j-reit"]):
        scheme = "reit_asset_transaction"
        asset_context = "reit_operating_asset"
        reasons.append("投資法人/J-REITキーワードを検知")

    return action, scheme, asset_context, reasons


def _judge_real_estate_candidate(
    *,
    text: str,
    action: str,
    scheme: str,
    asset_context: str,
) -> bool:
    if scheme == "not_applicable" or asset_context == "not_applicable":
        return False
    if scheme not in ("unknown_scheme", "not_applicable"):
        return True
    if action in ("sale", "acquisition", "reclassification", "development"):
        return _contains_any(text, ["固定資産", "不動産", "土地", "建物", "信託受益権", "販売用不動産"])
    return _contains_any(text, ["不動産", "土地", "建物", "信託受益権", "販売用不動産"])


def _judge_fixed_asset_bs_change_candidate(
    *,
    text: str,
    action: str,
    scheme: str,
) -> bool:
    if _contains_any(text, ["固定資産から販売用不動産", "保有目的の変更", "販売用不動産への振替"]):
        return True
    if scheme in ("direct_fixed_asset_transaction", "reclassification_to_inventory", "sale_and_leaseback"):
        return True
    if action in ("sale", "acquisition", "gain_loss_only") and _contains_any(
        text, ["固定資産", "販売用不動産", "信託受益権", "特別利益", "特別損失", "減損損失"]
    ):
        return True
    return False


def _judge_needs_document_reading(
    *,
    text: str,
    action: str,
    scheme: str,
) -> bool:
    if _contains_any(text, STRONG_FALSE_NEEDS_READING):
        return False
    if _contains_any(text, TRUE_NEEDS_READING_KEYWORDS):
        return True
    if scheme in ("trust_beneficiary_right_transaction", "inventory_real_estate_transaction", "reclassification_to_inventory"):
        return False
    if scheme in ("direct_fixed_asset_transaction", "indirect_possible_transaction", "sale_and_leaseback", "unknown_scheme"):
        return True
    if action in ("gain_loss_only", "change_or_revision", "completion_or_closing", "cancellation", "unknown"):
        return True
    return False


def _calculate_confidence(
    *,
    excluded: bool,
    is_real_estate_candidate: bool,
    scheme: str,
    action: str,
    needs_document_reading: bool,
    text: str,
) -> float:
    if excluded:
        return 0.95
    if not is_real_estate_candidate:
        return 0.25

    if scheme in ("inventory_real_estate_transaction", "trust_beneficiary_right_transaction", "reclassification_to_inventory"):
        return 0.95
    if scheme == "reit_asset_transaction":
        return 0.88
    if scheme == "sale_and_leaseback":
        return 0.68
    if scheme == "direct_fixed_asset_transaction":
        if _contains_any(text, ["物流センター", "工場用地", "倉庫", "店舗", "本社"]):
            return 0.72
        return 0.55
    if scheme == "indirect_possible_transaction":
        return 0.45
    if action == "gain_loss_only":
        return 0.25
    if needs_document_reading:
        return 0.5
    return 0.7


def _build_reason(
    *,
    excluded: bool,
    exclusion_hits: Sequence[str],
    action_hits: Sequence[str],
    scheme_hits: Sequence[str],
    context_hits: Sequence[str],
    consistency_reasons: Sequence[str],
    needs_document_reading: bool,
) -> str:
    if excluded:
        return f"{'、'.join(exclusion_hits[:3])} に関する開示であり、不動産取引ではないため"

    chunks: List[str] = []
    if action_hits:
        chunks.append(f"action根拠: {', '.join(action_hits[:3])}")
    if scheme_hits:
        chunks.append(f"scheme根拠: {', '.join(scheme_hits[:3])}")
    if context_hits:
        chunks.append(f"asset_context根拠: {', '.join(context_hits[:3])}")
    if consistency_reasons:
        chunks.append(f"補正: {', '.join(consistency_reasons[:2])}")
    chunks.append("本文確認必須" if needs_document_reading else "タイトル分類としては比較的明確")
    return " / ".join(chunks)


def classify_real_estate_title(title: Any, issuer_name: Any = None) -> Dict[str, Any]:
    title_norm = _normalize_text(title)
    issuer_norm = _normalize_text(issuer_name)

    if not title_norm:
        return {
            "is_fixed_asset_bs_change_candidate": False,
            "is_real_estate_transaction_candidate": False,
            "real_estate_asset_context_candidate": "not_applicable",
            "real_estate_transaction_scheme_candidate": "not_applicable",
            "real_estate_action_candidate": "not_applicable",
            "candidate_confidence": 0.0,
            "needs_document_reading": False,
            "classification_reason": "titleが空のため分類不可",
        }

    excluded, exclusion_hits = _is_clear_non_real_estate(title_norm)
    if excluded:
        return {
            "is_fixed_asset_bs_change_candidate": False,
            "is_real_estate_transaction_candidate": False,
            "real_estate_asset_context_candidate": "not_applicable",
            "real_estate_transaction_scheme_candidate": "not_applicable",
            "real_estate_action_candidate": "not_applicable",
            "candidate_confidence": 0.95,
            "needs_document_reading": False,
            "classification_reason": _build_reason(
                excluded=True,
                exclusion_hits=exclusion_hits,
                action_hits=[],
                scheme_hits=[],
                context_hits=[],
                consistency_reasons=[],
                needs_document_reading=False,
            ),
        }

    action, action_hits = _classify_by_priority(title_norm, ACTION_PRIORITY, "unknown")
    scheme, scheme_hits = _classify_by_priority(title_norm, SCHEME_PRIORITY, "unknown_scheme")
    asset_context, context_hits = _classify_by_priority(title_norm, ASSET_CONTEXT_PRIORITY, "unknown_real_estate")

    action, scheme, asset_context, consistency_reasons = _apply_consistency_rules(
        text=title_norm,
        issuer_name_text=issuer_norm,
        action=action,
        scheme=scheme,
        asset_context=asset_context,
    )

    is_real_estate_candidate = _judge_real_estate_candidate(
        text=title_norm,
        action=action,
        scheme=scheme,
        asset_context=asset_context,
    )
    needs_document_reading = _judge_needs_document_reading(
        text=title_norm,
        action=action,
        scheme=scheme,
    )
    confidence = _calculate_confidence(
        excluded=False,
        is_real_estate_candidate=is_real_estate_candidate,
        scheme=scheme,
        action=action,
        needs_document_reading=needs_document_reading,
        text=title_norm,
    )
    is_fixed_asset_bs_change_candidate = _judge_fixed_asset_bs_change_candidate(
        text=title_norm,
        action=action,
        scheme=scheme,
    )

    return {
        "is_fixed_asset_bs_change_candidate": bool(is_fixed_asset_bs_change_candidate),
        "is_real_estate_transaction_candidate": bool(is_real_estate_candidate),
        "real_estate_asset_context_candidate": asset_context if is_real_estate_candidate else "not_applicable",
        "real_estate_transaction_scheme_candidate": scheme if is_real_estate_candidate else "not_applicable",
        "real_estate_action_candidate": action if is_real_estate_candidate else "not_applicable",
        "candidate_confidence": round(float(confidence), 4),
        "needs_document_reading": bool(needs_document_reading),
        "classification_reason": _build_reason(
            excluded=False,
            exclusion_hits=[],
            action_hits=action_hits,
            scheme_hits=scheme_hits,
            context_hits=context_hits,
            consistency_reasons=consistency_reasons,
            needs_document_reading=needs_document_reading,
        ),
    }


def classify_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "title" not in work.columns:
        raise KeyError("input csv must contain 'title' column")
    if "company_name" not in work.columns:
        # fetch_tdnet_metadata.py 互換: issuer_name がなければ空で処理
        work["company_name"] = ""

    classified = [
        classify_real_estate_title(
            title=row.get("title", ""),
            issuer_name=row.get("company_name", ""),
        )
        for _, row in work.iterrows()
    ]
    cls_df = pd.DataFrame(classified)
    return pd.concat([work.reset_index(drop=True), cls_df.reset_index(drop=True)], axis=1)


def _to_yyyymmdd(value: str) -> str:
    txt = str(value or "").strip()
    if not txt:
        raise ValueError("date is empty")
    if re.fullmatch(r"\d{8}", txt):
        return txt
    dt = datetime.strptime(txt, "%Y-%m-%d")
    return dt.strftime("%Y%m%d")


def _date_range_inclusive(start_date: str, end_date: str) -> List[str]:
    start_txt = _to_yyyymmdd(start_date)
    end_txt = _to_yyyymmdd(end_date)
    start = datetime.strptime(start_txt, "%Y%m%d").date()
    end = datetime.strptime(end_txt, "%Y%m%d").date()
    if end < start:
        raise ValueError("END_DATE must be >= START_DATE")
    out: List[str] = []
    cur = start
    while cur <= end:
        out.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)
    return out


def _input_csv_path_for_day(yyyymmdd: str) -> str:
    return os.path.join(ORIGINAL_DIR, f"tdnet_metadata_{yyyymmdd}.csv")


def _output_csv_path_for_day(yyyymmdd: str) -> str:
    return os.path.join(CLASSIFIED_DIR, f"tdnet_metadata_{yyyymmdd}_real_estate_classified.csv")


def main() -> None:
    if not (START_DATE and END_DATE):
        raise ValueError("Set both START_DATE and END_DATE")
    target_dates = _date_range_inclusive(START_DATE, END_DATE)
    os.makedirs(CLASSIFIED_DIR, exist_ok=True)

    total_rows = 0
    saved_files: List[str] = []
    missing_dates: List[str] = []
    preview_df = pd.DataFrame()

    print(f"[info] range: {target_dates[0]} ~ {target_dates[-1]} (days={len(target_dates)})")
    for yyyymmdd in target_dates:
        input_csv = _input_csv_path_for_day(yyyymmdd)
        output_csv = _output_csv_path_for_day(yyyymmdd)

        if not os.path.exists(input_csv):
            missing_dates.append(yyyymmdd)
            print(f"[warn] skip (not found): {input_csv}")
            continue

        df = pd.read_csv(input_csv, dtype=str).fillna("")
        out_df = classify_dataframe(df)
        out_df.to_csv(output_csv, index=False, encoding=OUTPUT_ENCODING)

        total_rows += len(out_df)
        saved_files.append(output_csv)
        preview_df = out_df
        print(f"[done] {yyyymmdd}: rows={len(out_df)} saved={output_csv}")

    if not saved_files:
        raise RuntimeError("No daily input files found in the specified date range")

    print(f"\n[done] total rows: {total_rows}")
    print(f"[done] saved files: {len(saved_files)} under {CLASSIFIED_DIR}")
    if missing_dates:
        print(f"[warn] missing dates ({len(missing_dates)}): {', '.join(missing_dates)}")

    preview_cols = [
        "disclosure_date",
        "code",
        "company_name",
        "title",
        "is_real_estate_transaction_candidate",
        "real_estate_asset_context_candidate",
        "real_estate_transaction_scheme_candidate",
        "real_estate_action_candidate",
        "candidate_confidence",
        "needs_document_reading",
    ]
    show_cols = [c for c in preview_cols if c in preview_df.columns]
    if show_cols:
        print("\n[preview]")
        print(preview_df[show_cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
