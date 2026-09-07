# -*- coding: utf-8 -*-

# ==========================================
# 層化サンプル抽出（詳細設計 02 §8.1）
# Colab 1セル貼り付け実行OK
#
# 取得済みの全開示メタデータから、17業種区分 × source_type で層化した
# サンプル300件を抽出し、文書IDリストを data/samples/ に保存する。
#
#   - 17業種区分から各15〜20件
#   - source_type は実比率（timely 49.3 / earnings 31.3 /
#     presentation 13.1 / forecast 6.3）に合わせる
#   - ゲート通過を抽出条件にしない（誤検出と取りこぼしの両方を測るため）
#   - 乱数シードを固定し、試行間で同一サンプルを再現する
#
# 出力は preprocess_disclosures.py がそのまま入力にできる形にする。
# document_id は PDF の SHA256 が要るため、選抜後に実ファイルから採番する。
# ==========================================

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def _ensure_dependency(module_name: str, pip_name: Optional[str] = None) -> None:
    try:
        __import__(module_name)
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name or module_name])


_ensure_dependency("pandas")
_ensure_dependency("xlrd")

import pandas as pd


# -----------------------------
# 0) 設定（ここだけ編集すればOK）
# -----------------------------
# fetch_tdnet_metadata.py の出力先に合わせる。02§2 のDriveレイアウトとは
# ディレクトリ名が異なるが、実際に取得済みのパスを正とする。
ROOT_DIR = "/content/drive/MyDrive/git/prop_candidates/"
METADATA_DIR = ROOT_DIR + "data/original/"
MASTER_DIR = ROOT_DIR + "data/master/"
SAMPLE_DIR = ROOT_DIR + "data/samples/"

# PDFの探索先。上から順に存在するものを使う。
RAW_PDF_ROOT_DIRS: Sequence[str] = (
    ROOT_DIR + "data/raw/tdnet_pdfs/",
    ROOT_DIR + "data/original/pdf/",
)

JPX_LISTED_XLS = MASTER_DIR + "jpx_listed_202606.xls"
COMPANY_SEED_CSV = MASTER_DIR + "dim_company_seed.csv"

OUTPUT_SAMPLE_JSONL = SAMPLE_DIR + "stratified_sample_300.jsonl"
OUTPUT_SUMMARY_CSV = SAMPLE_DIR + "stratified_sample_300_summary.csv"
OUTPUT_ENCODING = "utf-8"

SAMPLE_SIZE = 300
SECTOR_MIN = 15
SECTOR_MAX = 20
RANDOM_SEED = 20260907

# 02§8.1 の実比率
SOURCE_TYPE_TARGET_RATIO: Dict[str, float] = {
    "timely_disclosure": 0.493,
    "earnings": 0.313,
    "earnings_presentation": 0.131,
    "forecast_revision": 0.063,
}

START_DATE = ""  # YYYY-MM-DD または YYYYMMDD。空なら全期間
END_DATE = ""

# PDFが実在する行だけを抽出対象にする。前処理で必ず落ちる行を
# サンプルに混ぜても、分類体系の検証には何も足さない。
REQUIRE_LOCAL_PDF = True


# -----------------------------
# 1) 文字列ユーティリティ
#    tdnet_pdf_preprocessing.py と同一の実装を写す（1セル完結のため）
# -----------------------------
def _date_to_compact(value: str) -> str:
    txt = str(value or "").strip()
    if not txt:
        return "unknown_date"
    txt = txt.replace("/", "-")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", txt)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    m2 = re.match(r"^(\d{8})$", txt)
    if m2:
        return txt
    return re.sub(r"\D+", "", txt)[:8] or "unknown_date"


def _safe_filename(value: str, default: str = "unknown") -> str:
    txt = (value or "").strip()
    txt = re.sub(r"[^0-9A-Za-z._-]+", "_", txt)
    txt = txt.strip("._")
    return txt or default


def _compute_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_document_id(disclosure_date: str, issuer_code: str, sha256_hex: str) -> str:
    yyyymmdd = _date_to_compact(disclosure_date)
    code = _safe_filename(str(issuer_code or "unknown_code"))
    return f"{yyyymmdd}_{code}_{sha256_hex[:8]}"


def _date_range_inclusive(start_date: str, end_date: str) -> List[str]:
    start = datetime.strptime(_date_to_compact(start_date), "%Y%m%d").date()
    end = datetime.strptime(_date_to_compact(end_date), "%Y%m%d").date()
    if end < start:
        raise ValueError("END_DATE must be >= START_DATE")
    out: List[str] = []
    cur = start
    while cur <= end:
        out.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)
    return out


# -----------------------------
# 2) source_type 判定（02§4.4 / 調査 2026-09-01 §2）
#    タイトルの正規表現のみで判定する。LLMは使わない。
#    ラベル付き236件（data/samples/tdnet_bodies_202608.jsonl）に対して
#    236/236 一致することを確認済み。
#    preprocess_disclosures.py にも同一の実装を置く（1セル完結のため）。
# -----------------------------
SOURCE_TYPE_RULES: Sequence[Tuple[str, str]] = (
    (
        "earnings_presentation",
        r"決算(補足説明資料|補足資料|説明資料|説明会資料|説明会|プレゼンテーション)"
        r"|(決算|業績)説明(会)?(資料|プレゼン)",
    ),
    ("earnings", r"決算短信"),
    (
        "forecast_revision",
        r"(業績|配当|通期|連結)?.{0,12}予想.{0,8}(修正|変更)|業績予想と実績値との差異",
    ),
)


def classify_source_type(title: str) -> str:
    txt = str(title or "")
    for source_type, pattern in SOURCE_TYPE_RULES:
        if re.search(pattern, txt):
            return source_type
    return "timely_disclosure"


# -----------------------------
# 3) 業種マスタ（17業種区分）
# -----------------------------
def _to_code4(code: Any) -> str:
    """TDnetの5桁コード（末尾0付き）を東証の4桁コードへ寄せる。

    2024年以降の英字入りコード（130A 等）があるため数字だけを取らない。
    """
    txt = str(code or "").strip().upper()
    if len(txt) == 5 and txt.endswith("0"):
        return txt[:4]
    return txt


def _find_column(columns: Iterable[Any], *keys: str) -> Optional[Any]:
    for col in columns:
        name = str(col)
        if all(k in name for k in keys):
            return col
    return None


def load_sector17_map() -> Dict[str, str]:
    """4桁コード → 17業種区分 の対応表を作る。

    第一候補はJPXの上場銘柄一覧。読めない場合は100社のシードCSVへ退避する。
    """
    if os.path.exists(JPX_LISTED_XLS):
        try:
            df = pd.read_excel(JPX_LISTED_XLS, dtype=str).fillna("")
            code_col = _find_column(df.columns, "コード")
            sector_col = _find_column(df.columns, "17業種区分") or _find_column(df.columns, "17業種")
            if code_col is not None and sector_col is not None:
                mapping = {
                    _to_code4(r[code_col]): str(r[sector_col]).strip()
                    for _, r in df.iterrows()
                    if str(r[code_col]).strip() and str(r[sector_col]).strip()
                }
                print(f"[info] sector17 from jpx_listed: {len(mapping)} codes")
                return mapping
            print(f"[warn] jpx_listed columns not recognized: {list(df.columns)}")
        except Exception as e:
            print(f"[warn] failed to read jpx_listed: {type(e).__name__}: {e}")

    if os.path.exists(COMPANY_SEED_CSV):
        df = pd.read_csv(COMPANY_SEED_CSV, dtype=str, encoding="utf-8-sig").fillna("")
        mapping = {
            _to_code4(r["company_id"]): str(r["jpx_sector_17"]).strip()
            for _, r in df.iterrows()
            if str(r.get("company_id", "")).strip()
        }
        print(f"[warn] falling back to dim_company_seed: {len(mapping)} codes")
        return mapping

    raise FileNotFoundError(f"no sector master found: {JPX_LISTED_XLS} / {COMPANY_SEED_CSV}")


# -----------------------------
# 4) メタデータとPDFの突合
# -----------------------------
def _resolve_pdf_root() -> Optional[str]:
    for root in RAW_PDF_ROOT_DIRS:
        if os.path.exists(root):
            return root
    return None


def build_pdf_index(root_dir: str) -> Dict[str, List[str]]:
    """{yyyymmdd: [pdf paths]} を作る。"""
    by_date: Dict[str, List[str]] = defaultdict(list)
    for dp, _, files in os.walk(root_dir):
        for name in files:
            if not name.lower().endswith(".pdf"):
                continue
            path = os.path.join(dp, name)
            m = re.search(r"(\d{8})", path)
            if m:
                by_date[m.group(1)].append(path)
    return by_date


def resolve_pdf_path(row: pd.Series, by_date: Dict[str, List[str]], day: str) -> Optional[str]:
    """fetch_tdnet_metadata.py の命名規則に沿ってPDFを引く。"""
    explicit = str(row.get("pdf_local_path", "") or "").strip()
    if explicit and os.path.exists(explicit):
        return explicit

    scoped = by_date.get(day, [])
    if not scoped:
        return None

    document_url = str(row.get("document_url", "") or "").strip()
    if document_url:
        basename = os.path.basename(document_url)
        stem = os.path.splitext(basename)[0]
        for p in scoped:
            if stem and stem in os.path.basename(p):
                return p

    code = str(row.get("code", "") or "").strip()
    disclosure_number = str(row.get("disclosure_number", "") or "").strip()
    if disclosure_number:
        for p in scoped:
            bn = os.path.basename(p)
            if disclosure_number in bn and (not code or code in bn):
                return p
    return None


def load_all_metadata() -> pd.DataFrame:
    if not os.path.exists(METADATA_DIR):
        raise FileNotFoundError(f"metadata dir not found: {METADATA_DIR}")

    pattern = re.compile(r"^tdnet_metadata_(\d{8})\.csv$")
    days: List[str] = []
    for name in sorted(os.listdir(METADATA_DIR)):
        m = pattern.match(name)
        if m:
            days.append(m.group(1))
    if not days:
        raise RuntimeError(f"no tdnet_metadata_yyyymmdd.csv under: {METADATA_DIR}")

    if START_DATE or END_DATE:
        if not (START_DATE and END_DATE):
            raise ValueError("If using date range, set both START_DATE and END_DATE")
        allowed = set(_date_range_inclusive(START_DATE, END_DATE))
        days = [d for d in days if d in allowed]

    frames: List[pd.DataFrame] = []
    for day in days:
        path = os.path.join(METADATA_DIR, f"tdnet_metadata_{day}.csv")
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
        df["disclosure_date_compact"] = day
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True)
    before = len(merged)
    merged["_dedupe_key"] = (
        merged["disclosure_date_compact"].astype(str)
        + "|"
        + merged.get("code", pd.Series([""] * len(merged))).astype(str)
        + "|"
        + merged.get("document_url", pd.Series([""] * len(merged))).astype(str)
    )
    merged = merged.drop_duplicates(subset=["_dedupe_key"], keep="last").drop(columns=["_dedupe_key"])
    print(f"[info] metadata days={len(days)} rows={before} -> deduped={len(merged)}")
    return merged.reset_index(drop=True)


# -----------------------------
# 5) 層化抽出
# -----------------------------
def _allocate_sector_quota(supply: Dict[str, int], total: int) -> Dict[str, int]:
    """業種ごとの割当件数を決める。

    まず均等割りし、SECTOR_MIN〜SECTOR_MAX と実在件数で頭打ちにする。
    余った枠は空きのある業種へ順に配り直す。
    """
    sectors = sorted(supply.keys())
    if not sectors:
        return {}

    base = total // len(sectors)
    remainder = total - base * len(sectors)
    quota: Dict[str, int] = {}
    for i, sector in enumerate(sectors):
        want = base + (1 if i < remainder else 0)
        want = max(SECTOR_MIN, min(SECTOR_MAX, want))
        quota[sector] = min(want, supply[sector])

    # 不足分を、上限と実在件数に余裕のある業種へ配り直す
    guard = 0
    while sum(quota.values()) != total and guard < 10000:
        guard += 1
        diff = total - sum(quota.values())
        if diff > 0:
            candidates = [s for s in sectors if quota[s] < min(SECTOR_MAX, supply[s])]
            if not candidates:
                # SECTOR_MAX を超えてでも件数を満たす。層化の均等性より総数を優先する。
                candidates = [s for s in sectors if quota[s] < supply[s]]
            if not candidates:
                break
            for sector in candidates:
                if sum(quota.values()) >= total:
                    break
                quota[sector] += 1
        else:
            candidates = [s for s in sectors if quota[s] > SECTOR_MIN]
            if not candidates:
                candidates = [s for s in sectors if quota[s] > 0]
            if not candidates:
                break
            for sector in candidates:
                if sum(quota.values()) <= total:
                    break
                quota[sector] -= 1
    return quota


def _allocate_source_type_quota(quota: int, available: Dict[str, int]) -> Dict[str, int]:
    """業種内で source_type の割当件数を決める。実比率に寄せる。"""
    order = sorted(SOURCE_TYPE_TARGET_RATIO.keys(), key=lambda k: -SOURCE_TYPE_TARGET_RATIO[k])
    want: Dict[str, int] = {}
    for st in order:
        want[st] = min(available.get(st, 0), int(round(quota * SOURCE_TYPE_TARGET_RATIO[st])))

    # 実比率で割り切れない分・在庫不足分を、余っている source_type へ回す
    guard = 0
    while sum(want.values()) < quota and guard < 10000:
        guard += 1
        candidates = [st for st in order if want[st] < available.get(st, 0)]
        if not candidates:
            break
        for st in candidates:
            if sum(want.values()) >= quota:
                break
            want[st] += 1
    while sum(want.values()) > quota:
        for st in reversed(order):
            if sum(want.values()) <= quota:
                break
            if want[st] > 0:
                want[st] -= 1
    return want


def stratified_sample(df: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
    pools: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))
    for idx, row in df.iterrows():
        pools[str(row["jpx_sector_17"])][str(row["source_type"])].append(idx)
    for sector in pools:
        for st in pools[sector]:
            rng.shuffle(pools[sector][st])

    supply = {sector: sum(len(v) for v in by_st.values()) for sector, by_st in pools.items()}
    sector_quota = _allocate_sector_quota(supply, SAMPLE_SIZE)

    selected: List[int] = []
    for sector in sorted(sector_quota.keys()):
        quota = sector_quota[sector]
        if quota <= 0:
            continue
        available = {st: len(v) for st, v in pools[sector].items()}
        st_quota = _allocate_source_type_quota(quota, available)
        for st, n in st_quota.items():
            selected.extend(pools[sector][st][:n])

    out = df.loc[selected].copy()
    out = out.sample(frac=1.0, random_state=RANDOM_SEED).reset_index(drop=True)
    return out


# -----------------------------
# 6) main
# -----------------------------
def main() -> None:
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    rng = random.Random(RANDOM_SEED)

    df = load_all_metadata()
    df["source_type"] = df["title"].apply(classify_source_type)
    df["code4"] = df["code"].apply(_to_code4)

    sector_map = load_sector17_map()
    df["jpx_sector_17"] = df["code4"].map(sector_map).fillna("")

    unmatched = int((df["jpx_sector_17"] == "").sum())
    df = df[df["jpx_sector_17"] != ""].copy()
    print(f"[info] sector matched={len(df)} unmatched_dropped={unmatched}")

    if REQUIRE_LOCAL_PDF:
        pdf_root = _resolve_pdf_root()
        if not pdf_root:
            raise FileNotFoundError(f"no pdf root found among: {list(RAW_PDF_ROOT_DIRS)}")
        by_date = build_pdf_index(pdf_root)
        print(f"[info] pdf root={pdf_root} indexed_days={len(by_date)} "
              f"files={sum(len(v) for v in by_date.values())}")
        df["pdf_path"] = [
            resolve_pdf_path(row, by_date, str(row["disclosure_date_compact"]))
            for _, row in df.iterrows()
        ]
        missing = int(df["pdf_path"].isna().sum())
        df = df[df["pdf_path"].notna()].copy()
        print(f"[info] pdf resolved={len(df)} missing_dropped={missing}")
    else:
        df["pdf_path"] = None

    df = df.reset_index(drop=True)
    print(f"[info] population={len(df)} sectors={df['jpx_sector_17'].nunique()}")
    print(f"[info] population source_type={dict(Counter(df['source_type']))}")

    sample = stratified_sample(df, rng)
    print(f"[info] sampled={len(sample)}")

    rows: List[Dict[str, Any]] = []
    for i, row in sample.iterrows():
        pdf_path = row["pdf_path"]
        sha256_hex = ""
        document_id = ""
        if pdf_path and os.path.exists(pdf_path):
            try:
                sha256_hex = _compute_sha256(pdf_path)
                document_id = _build_document_id(
                    disclosure_date=str(row.get("disclosure_date", "")),
                    issuer_code=str(row.get("code", "")),
                    sha256_hex=sha256_hex,
                )
            except Exception as e:
                print(f"[warn] sha256 failed: {pdf_path}: {type(e).__name__}: {e}")
        rows.append(
            {
                "document_id": document_id,
                "disclosure_date": str(row.get("disclosure_date", "")),
                "disclosure_time": str(row.get("disclosure_time", "")),
                "disclosure_number": str(row.get("disclosure_number", "")),
                "code": str(row.get("code", "")),
                "code4": str(row.get("code4", "")),
                "company_name": str(row.get("company_name", "")),
                "title": str(row.get("title", "")),
                "source_type": str(row.get("source_type", "")),
                "jpx_sector_17": str(row.get("jpx_sector_17", "")),
                "document_url": str(row.get("document_url", "")),
                "pdf_path": str(pdf_path or ""),
                "pdf_sha256": sha256_hex,
            }
        )
        if (i + 1) % 50 == 0:
            print(f"[info] sha256 {i + 1}/{len(sample)}")

    with open(OUTPUT_SAMPLE_JSONL, "w", encoding=OUTPUT_ENCODING) as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary_rows: List[Dict[str, Any]] = []
    by_sector: Counter = Counter(r["jpx_sector_17"] for r in rows)
    by_sector_st: Counter = Counter((r["jpx_sector_17"], r["source_type"]) for r in rows)
    for sector in sorted(by_sector):
        entry: Dict[str, Any] = {"jpx_sector_17": sector, "total": by_sector[sector]}
        for st in SOURCE_TYPE_TARGET_RATIO:
            entry[st] = by_sector_st.get((sector, st), 0)
        summary_rows.append(entry)
    total_entry: Dict[str, Any] = {"jpx_sector_17": "__total__", "total": len(rows)}
    for st in SOURCE_TYPE_TARGET_RATIO:
        total_entry[st] = sum(1 for r in rows if r["source_type"] == st)
    summary_rows.append(total_entry)
    pd.DataFrame(summary_rows).to_csv(OUTPUT_SUMMARY_CSV, index=False, encoding="utf-8-sig")

    print("\n[done] stratified sample")
    print(f"[done] sample : {OUTPUT_SAMPLE_JSONL} ({len(rows)} docs)")
    print(f"[done] summary: {OUTPUT_SUMMARY_CSV}")
    print(f"[done] sectors: {len(by_sector)} "
          f"min={min(by_sector.values())} max={max(by_sector.values())}")
    achieved = {st: total_entry[st] for st in SOURCE_TYPE_TARGET_RATIO}
    print(f"[done] source_type counts={achieved}")
    for st, n in achieved.items():
        print(f"[done]   {st}: {n / max(1, len(rows)) * 100:.1f}% "
              f"(target {SOURCE_TYPE_TARGET_RATIO[st] * 100:.1f}%)")
    missing_id = sum(1 for r in rows if not r["document_id"])
    if missing_id:
        print(f"[warn] document_id could not be assigned for {missing_id} rows")


if __name__ == "__main__":
    main()
