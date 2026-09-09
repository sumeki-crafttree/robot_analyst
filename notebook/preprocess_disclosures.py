# -*- coding: utf-8 -*-

# ==========================================
# 適時開示PDF 前処理（詳細設計 02 §4）
# Colab 1セル貼り付け実行OK
#
# PDF → 1文書1行のJSONL（1日1ファイル）。
#
# tdnet_pdf_preprocessing.py からの変更は「出力形式だけ」である。
# 動作実績のある処理ロジックには手を入れていない。
#   - PyMuPDFのブロック抽出 / pdfplumberのテーブル抽出
#   - ページレイアウト判定（SCAN_TEXT_CHAR_THRESHOLD / SCAN_IMAGE_AREA_THRESHOLD）
#   - ヘッダ・フッタの繰り返し検出
#   - 文字列正規化（_normalize_text / _normalize_for_match）
# は現行の実装をそのまま写している。
#
# 追加したのは 02§4.4 の3点だけである。
#   - 暗号化PDFの復号（cryptography）
#   - source_type のタイトル正規表現判定
#   - スキャンPDFの skipped_scan 扱い
#
# セッション断に備え、1件処理するごとに追記保存する（02§8.3）。
# 起動時に出力JSONLを読み、処理済み document_id はスキップする。
# ==========================================

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


def _ensure_dependency(module_name: str, pip_name: Optional[str] = None) -> None:
    try:
        __import__(module_name)
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name or module_name])


_ensure_dependency("pandas")
_ensure_dependency("fitz", "pymupdf")
_ensure_dependency("pdfplumber")
# TDnetにはAES暗号化PDFが混じる。これが無いと pdfminer 系がテキスト抽出に失敗し、
# 件数が少ないため握り潰されると気づかない（02§4.4）。
_ensure_dependency("cryptography")

import fitz  # type: ignore
import pandas as pd
import pdfplumber  # type: ignore


# -----------------------------
# 0) 設定（ここだけ編集すればOK）
# -----------------------------
ROOT_DIR = "/content/drive/MyDrive/git/prop_candidates/"
METADATA_DIR = ROOT_DIR + "data/original/"
SAMPLE_DIR = ROOT_DIR + "data/samples/"
PROCESSED_DIR = ROOT_DIR + "data/processed/"
OUTPUT_ENCODING = "utf-8"

# ログはプロジェクト直下にまとめる。data/ や models/ と同じ並び。
LOG_DIR = ROOT_DIR + "log/"
# Colabはセッションが切れると出力が消える。LOG_DIR（Drive上）へ標準出力と
# 標準エラーを複製し、切断後も経過を追えるようにする。
LOG_TO_FILE = True
# fitz/pdfplumber や外部プロセスは fd 2 へ直接書くため、sys.stderr の
# 差し替えでは拾えない。fdごと複製する。
LOG_CAPTURE_NATIVE_STDERR = True
# ログのファイル名に入れる。セルに貼り付けると __file__ が無いので定数で持つ。
SCRIPT_NAME = "preprocess_disclosures"

RAW_PDF_ROOT_DIRS: Sequence[str] = (
    ROOT_DIR + "data/raw/tdnet_pdfs/",
    ROOT_DIR + "data/original/pdf/",
)

# 処理対象の選び方
#   USE_SAMPLE = True   build_sample.py の層化サンプル300件だけを処理する（02§8.1）
#   USE_SAMPLE = False  層化抽出を通さず、fetch_tdnet_metadata.py の日次CSV
#                       （tdnet_metadata_{yyyymmdd}.csv）を全件処理する。
#                       日付を絞りたいときだけ START_DATE / END_DATE を埋める。
#                       空なら METADATA_DIR にある全日付が対象になる。
#
# 全件は約9,400件・前処理だけで約9.8時間かかる（02§8.1）。1回のColabセッションでは
# 終わらない前提で、途中で切れても再実行すれば続きから進む（下の再開処理）。
SAMPLE_JSONL = SAMPLE_DIR + "stratified_sample_300.jsonl"
USE_SAMPLE = True

# USE_SAMPLE=False のときだけ使う日付範囲。両方空なら全期間。
START_DATE = ""  # YYYY-MM-DD または YYYYMMDD
END_DATE = ""

MAX_DOCUMENTS: Optional[int] = None

# JSONLに加えてCSVも出す。CSVはExcelで開ける一覧であり、本文とブロックは載せない。
# 本文は1件平均13,855字（決算短信）でExcelのセル上限32,767字を超える場合があるため、
# 既定では除外する。必要なら CSV_INCLUDE_TEXT=True にする。
WRITE_CSV = True
CSV_INCLUDE_TEXT = False
CSV_ENCODING = "utf-8-sig"  # BOM付き。Excelで開いたときに日本語が化けないようにする。

# --- ここから下は tdnet_pdf_preprocessing.py と同一値 ---
SCAN_TEXT_CHAR_THRESHOLD = 40
SCAN_IMAGE_AREA_THRESHOLD = 0.35
SLIDE_ASPECT_THRESHOLD = 1.2
DOC_TEXT_CHAR_THRESHOLD = 250


# -----------------------------
# 1) 文字列正規化（現行実装をそのまま）
# -----------------------------
def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    txt = unicodedata.normalize("NFKC", str(value))
    txt = txt.replace("　", " ")
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _normalize_for_match(value: Any) -> str:
    txt = _normalize_text(value).lower()
    txt = re.sub(r"[\s・･/／（）()「」『』【】\[\]]+", "", txt)
    return txt


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


def _sha256_of_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:8]


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
# 2) source_type 判定（02§4.4）
#    build_sample.py と同一の実装。ラベル付き236件に対し236/236一致。
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
# 3) ブロック・テーブル・レイアウト（現行実装をそのまま）
# -----------------------------
def _guess_block_type(text: str, page_number: int, block_order: int) -> str:
    t = _normalize_text(text)
    if not t:
        return "unknown"
    if page_number == 1 and block_order == 1:
        return "document_title"
    if re.match(r"^[0-9０-９]+[\.．]\s*", t):
        return "section_heading"
    if t.startswith(("・", "-", "●", "■")):
        return "bullet"
    if len(t) <= 40 and ("に関するお知らせ" in t or "のお知らせ" in t):
        return "page_title"
    if len(t) <= 30 and re.search(r"(注|※|免責|お問い合わせ)", t):
        return "note"
    return "paragraph"


def _compute_block_quality(text: str, extraction_method: str = "pymupdf_text") -> float:
    t = str(text or "")
    if not t.strip():
        return 0.1
    mojibake_penalty = 0.2 if "�" in t else 0.0
    length_bonus = min(0.35, len(t) / 400.0)
    method_bonus = 0.2 if extraction_method == "pymupdf_text" else 0.1
    score = 0.35 + length_bonus + method_bonus - mojibake_penalty
    return max(0.0, min(1.0, round(score, 4)))


def _table_to_markdown(rows: List[List[str]]) -> str:
    clean_rows = [[_normalize_text(c) for c in r] for r in rows if r]
    clean_rows = [r for r in clean_rows if any(x for x in r)]
    if not clean_rows:
        return ""
    width = max(len(r) for r in clean_rows)
    padded = [r + [""] * (width - len(r)) for r in clean_rows]
    head = padded[0]
    sep = ["---"] * width
    lines = [
        "| " + " | ".join(head) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for r in padded[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def _classify_page_layout(stats: Dict[str, Any]) -> str:
    aspect = float(stats["page_aspect_ratio"])
    text_char_count = int(stats["text_char_count"])
    text_block_count = int(stats["text_block_count"])
    image_area_ratio = float(stats["image_area_ratio"])
    table_count = int(stats["detected_table_count"])
    avg_len = float(stats["average_text_block_length"])

    if text_char_count <= SCAN_TEXT_CHAR_THRESHOLD and image_area_ratio >= SCAN_IMAGE_AREA_THRESHOLD:
        return "scanned_or_image"
    if table_count >= 2:
        return "table_heavy"
    if aspect >= SLIDE_ASPECT_THRESHOLD and text_block_count >= 4 and avg_len <= 80:
        return "slide_like"
    if text_char_count >= DOC_TEXT_CHAR_THRESHOLD and avg_len >= 20:
        return "doc_like"
    if table_count == 1 and text_char_count < 200:
        return "table_heavy"
    return "doc_like"


def _infer_pdf_layout_type(page_layouts: List[str]) -> str:
    if not page_layouts:
        return "unknown"
    c = Counter(page_layouts)
    top_label, top_count = c.most_common(1)[0]
    if len(c) > 1 and top_count / len(page_layouts) < 0.7:
        return "mixed"
    return top_label


def _is_repeated_header_footer(
    text_norm: str, page_count: int, freq: int, y0: float, y1: float, page_height: float
) -> str:
    if page_count < 2 or freq < 2 or not text_norm:
        return ""
    top_th = page_height * 0.12
    bottom_th = page_height * 0.88
    if y1 <= top_th:
        return "header"
    if y0 >= bottom_th:
        return "footer"
    return ""


# -----------------------------
# 4) 1文書の処理 → 1レコード（02§4.2）
# -----------------------------
def _open_pdf(pdf_path: str) -> "fitz.Document":
    """暗号化PDFは空パスワードで復号を試みる（02§4.4）。"""
    doc = fitz.open(pdf_path)
    if getattr(doc, "needs_pass", False):
        if not doc.authenticate(""):
            doc.close()
            raise RuntimeError("encrypted pdf: failed to authenticate with empty password")
    return doc


def process_one_pdf(meta: Dict[str, Any], pdf_path: str) -> Dict[str, Any]:
    disclosure_date = str(meta.get("disclosure_date", "") or "")
    issuer_code = str(meta.get("code", "") or "")
    title = str(meta.get("title", "") or "")

    sha256_hex = str(meta.get("pdf_sha256", "") or "") or _compute_sha256(pdf_path)
    document_id = str(meta.get("document_id", "") or "") or _build_document_id(
        disclosure_date=disclosure_date, issuer_code=issuer_code, sha256_hex=sha256_hex
    )

    record: Dict[str, Any] = {
        "document_id": document_id,
        "disclosure_date": disclosure_date,
        "disclosure_time": str(meta.get("disclosure_time", "") or ""),
        "code": issuer_code,
        "company_name": str(meta.get("company_name", "") or ""),
        "title": title,
        "source_type": str(meta.get("source_type", "") or "") or classify_source_type(title),
        "jpx_sector_17": str(meta.get("jpx_sector_17", "") or ""),
        "document_url": str(meta.get("document_url", "") or ""),
        "pdf_sha256": sha256_hex,
        "page_count": 0,
        "char_count": 0,
        "pdf_layout_type": "unknown",
        "text": "",
        "blocks": [],
        "status": "ok",
        "error": None,
    }

    blocks_out: List[Dict[str, Any]] = []
    page_layouts: List[str] = []
    page_texts: List[str] = []
    errors: List[str] = []

    doc = _open_pdf(pdf_path)
    try:
        with pdfplumber.open(pdf_path, password="") as plumber_doc:
            page_count = len(doc)
            # 内部保持用。出力には i / page / text / type の4項目しか出さない（02§4.2）。
            internal: List[Dict[str, Any]] = []
            normalized_counter: Counter = Counter()
            block_positions: List[Tuple[int, int, float, float, float]] = []

            for i in range(page_count):
                page_number = i + 1
                page = doc[i]
                p_page = plumber_doc.pages[i] if i < len(plumber_doc.pages) else None

                rect = page.rect
                page_width = float(rect.width or 1.0)
                page_height = float(rect.height or 1.0)
                aspect_ratio = page_width / max(1.0, page_height)

                text_blocks_raw = page.get_text("blocks")
                text_blocks = [b for b in text_blocks_raw if len(b) >= 5 and _normalize_text(b[4])]
                text_blocks = sorted(
                    text_blocks, key=lambda x: (round(float(x[1]), 1), round(float(x[0]), 1))
                )
                extracted_text = page.get_text("text") or ""
                text_char_count = len(_normalize_text(extracted_text))
                page_texts.append(_normalize_text(extracted_text))

                image_count = len(page.get_images(full=True))
                image_area_ratio = 0.0
                page_dict = page.get_text("dict")
                if page_dict and "blocks" in page_dict:
                    image_area = 0.0
                    for b in page_dict["blocks"]:
                        if b.get("type") == 1 and "bbox" in b:
                            x0, y0, x1, y1 = b["bbox"]
                            image_area += max(0.0, (x1 - x0)) * max(0.0, (y1 - y0))
                    page_area = max(1.0, page_width * page_height)
                    image_area_ratio = image_area / page_area

                table_rows_list: List[List[List[str]]] = []
                if p_page is not None:
                    try:
                        extracted_tables = p_page.extract_tables() or []
                        for t in extracted_tables:
                            if t and any(
                                any(_normalize_text(c) for c in row_cells if c is not None)
                                for row_cells in t
                            ):
                                table_rows_list.append(
                                    [[_normalize_text(c) for c in (r or [])] for r in t if r is not None]
                                )
                    except Exception as te:
                        errors.append(f"table_extract_error_page_{page_number}: {te}")
                detected_table_count = len(table_rows_list)

                avg_text_block_length = 0.0
                if text_blocks:
                    avg_text_block_length = sum(
                        len(_normalize_text(b[4])) for b in text_blocks
                    ) / len(text_blocks)

                stats = {
                    "page_aspect_ratio": round(aspect_ratio, 4),
                    "text_char_count": text_char_count,
                    "text_block_count": len(text_blocks),
                    "image_count": image_count,
                    "image_area_ratio": round(image_area_ratio, 4),
                    "detected_table_count": detected_table_count,
                    "average_text_block_length": round(avg_text_block_length, 4),
                }
                page_layout_type = _classify_page_layout(stats)
                page_layouts.append(page_layout_type)

                for j, b in enumerate(text_blocks, 1):
                    x0, y0, x1, y1, text = b[:5]
                    text_norm = _normalize_text(text)
                    rec = {
                        "page": page_number,
                        "text": text_norm,
                        "type": _guess_block_type(text_norm, page_number, j),
                        "_normalized_text": _normalize_for_match(text_norm),
                        "_quality": _compute_block_quality(text_norm, "pymupdf_text"),
                    }
                    internal.append(rec)
                    normalized_counter[rec["_normalized_text"]] += 1
                    block_positions.append(
                        (len(internal) - 1, page_number, float(y0), float(y1), page_height)
                    )

                # テーブルは別配列にせず blocks に type="table" で混ぜる（02§4.2）。
                # 当該ページの末尾に置くことでページ順は保たれる。
                for rows in table_rows_list:
                    md_table = _table_to_markdown(rows)
                    if not md_table:
                        continue
                    internal.append(
                        {
                            "page": page_number,
                            "text": md_table,
                            "type": "table",
                            "_normalized_text": _normalize_for_match(md_table),
                            "_quality": 0.5,
                        }
                    )

            # ヘッダ・フッタの繰り返し検出（現行実装をそのまま）
            for block_idx, page_number, y0, y1, page_height in block_positions:
                b = internal[block_idx]
                repeated_type = _is_repeated_header_footer(
                    text_norm=b["_normalized_text"],
                    page_count=page_count,
                    freq=normalized_counter.get(b["_normalized_text"], 0),
                    y0=y0,
                    y1=y1,
                    page_height=page_height,
                )
                if repeated_type:
                    b["type"] = repeated_type

            for i, b in enumerate(internal):
                blocks_out.append({"i": i, "page": b["page"], "text": b["text"], "type": b["type"]})

            pdf_layout_type = _infer_pdf_layout_type(page_layouts)
            full_text = "\n".join(t for t in page_texts if t)

            record["page_count"] = page_count
            record["pdf_layout_type"] = pdf_layout_type
            record["blocks"] = blocks_out
            record["text"] = full_text
            record["char_count"] = len(full_text)

            # スキャンPDFはOCRしない。本文を空にして skipped_scan とする（02§4.4）。
            if pdf_layout_type == "scanned_or_image":
                record["status"] = "skipped_scan"
                record["text"] = ""
                record["char_count"] = 0
                record["blocks"] = []

            if errors:
                record["error"] = "; ".join(errors)
            return record
    finally:
        doc.close()


# -----------------------------
# 5) 対象の決定
# -----------------------------
def _resolve_pdf_root() -> Optional[str]:
    for root in RAW_PDF_ROOT_DIRS:
        if os.path.exists(root):
            return root
    return None


def _build_pdf_index(root_dir: str) -> Dict[str, List[str]]:
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


def _resolve_pdf_path(meta: Dict[str, Any], by_date: Dict[str, List[str]], day: str) -> Optional[str]:
    explicit = str(meta.get("pdf_path", "") or meta.get("pdf_local_path", "") or "").strip()
    if explicit and os.path.exists(explicit):
        return explicit

    scoped = by_date.get(day, [])
    if not scoped:
        return None

    document_url = str(meta.get("document_url", "") or "").strip()
    if document_url:
        stem = os.path.splitext(os.path.basename(document_url))[0]
        for p in scoped:
            if stem and stem in os.path.basename(p):
                return p

    code = str(meta.get("code", "") or "").strip()
    disclosure_number = str(meta.get("disclosure_number", "") or "").strip()
    if disclosure_number:
        for p in scoped:
            bn = os.path.basename(p)
            if disclosure_number in bn and (not code or code in bn):
                return p
    return None


def load_targets() -> List[Dict[str, Any]]:
    if USE_SAMPLE:
        if not os.path.exists(SAMPLE_JSONL):
            raise FileNotFoundError(
                f"sample not found: {SAMPLE_JSONL}\n"
                "build_sample.py を先に実行するか、USE_SAMPLE=False にしてください。"
            )
        targets = [json.loads(line) for line in open(SAMPLE_JSONL, encoding="utf-8") if line.strip()]
        print(f"[info] targets from sample: {len(targets)}")
        return targets

    if not os.path.exists(METADATA_DIR):
        raise FileNotFoundError(f"metadata dir not found: {METADATA_DIR}")
    pattern = re.compile(r"^tdnet_metadata_(\d{8})\.csv$")
    days = sorted(m.group(1) for m in (pattern.match(n) for n in os.listdir(METADATA_DIR)) if m)
    if START_DATE or END_DATE:
        if not (START_DATE and END_DATE):
            raise ValueError("If using date range, set both START_DATE and END_DATE")
        allowed = set(_date_range_inclusive(START_DATE, END_DATE))
        days = [d for d in days if d in allowed]

    targets: List[Dict[str, Any]] = []
    seen_keys: Set[str] = set()
    duplicates = 0
    for day in days:
        df = pd.read_csv(
            os.path.join(METADATA_DIR, f"tdnet_metadata_{day}.csv"), dtype=str, encoding="utf-8-sig"
        ).fillna("")
        for _, row in df.iterrows():
            meta = {k: str(v) for k, v in row.to_dict().items()}
            meta["source_type"] = classify_source_type(meta.get("title", ""))
            key = _source_key(meta)
            if key in seen_keys:
                duplicates += 1
                continue
            seen_keys.add(key)
            targets.append(meta)
    print(f"[info] targets from metadata: {len(targets)} days={len(days)} duplicates_dropped={duplicates}")
    if len(targets) > 1000:
        print(
            f"[warn] 全件処理は {len(targets)} 件。1件あたり約3.8秒として約"
            f"{len(targets) * 3.8 / 3600:.1f} 時間かかる。"
            " Colabのセッションは切れる前提で、切れたら再実行すれば続きから進む。"
        )
    return targets


# -----------------------------
# 6) 再開可能性（02§8.3）
# -----------------------------
def _output_path_for_day(day: str) -> str:
    return os.path.join(PROCESSED_DIR, f"disclosures_{day}.jsonl")


def _csv_path_for_day(day: str) -> str:
    return os.path.join(PROCESSED_DIR, f"disclosures_{day}.csv")


def _source_key(meta: Dict[str, Any]) -> str:
    """PDFを開く前に決まる、開示1件を一意に指すキー。

    document_id は PDF の SHA256 を含むため、PDFを開くまで確定しない。
    層化サンプル経由なら build_sample.py が採番済みだが、日次CSVを直接読む
    場合は未確定であり、document_id だけでは再開時にスキップ判定ができない。
    そのため URL（無ければ日付+コード+タイトル）を再開キーとして併用する。
    """
    url = str(meta.get("document_url", "") or "").strip()
    if url:
        return url
    return "|".join(
        [
            _date_to_compact(str(meta.get("disclosure_date", ""))),
            str(meta.get("code", "") or ""),
            _normalize_text(meta.get("title", "")),
        ]
    )


def load_processed(days: Iterable[str]) -> Tuple[Set[str], Set[str]]:
    """出力JSONLを読み、処理済みの document_id と再開キーを集める。"""
    ids: Set[str] = set()
    keys: Set[str] = set()
    for day in sorted(set(days)):
        path = _output_path_for_day(day)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("document_id"):
                    ids.add(rec["document_id"])
                keys.add(_source_key(rec))
    return ids, keys


CSV_BASE_FIELDS: Sequence[str] = (
    "document_id",
    "disclosure_date",
    "disclosure_time",
    "code",
    "company_name",
    "title",
    "source_type",
    "jpx_sector_17",
    "document_url",
    "pdf_sha256",
    "page_count",
    "char_count",
    "block_count",
    "table_block_count",
    "pdf_layout_type",
    "status",
    "error",
)


def csv_fields() -> List[str]:
    fields = list(CSV_BASE_FIELDS)
    if CSV_INCLUDE_TEXT:
        fields.append("text")
    return fields


def record_to_csv_row(record: Dict[str, Any]) -> Dict[str, Any]:
    blocks = record.get("blocks") or []
    row = {k: record.get(k, "") for k in CSV_BASE_FIELDS if k not in ("block_count", "table_block_count")}
    row["block_count"] = len(blocks)
    row["table_block_count"] = sum(1 for b in blocks if b.get("type") == "table")
    if CSV_INCLUDE_TEXT:
        row["text"] = record.get("text", "")
    return row


def open_csv_appender(path: str):
    """追記用のCSVを開く。新規または空のときだけヘッダを書く。"""
    import csv

    is_new = (not os.path.exists(path)) or os.path.getsize(path) == 0
    handle = open(path, "a", encoding=CSV_ENCODING, newline="")
    writer = csv.DictWriter(handle, fieldnames=csv_fields(), extrasaction="ignore")
    if is_new:
        writer.writeheader()
        handle.flush()
    return handle, writer


# -----------------------------
# 7) main
# -----------------------------
def _log_path() -> str:
    """<LOG_DIR>/<日時>_<スクリプト名>.txt

    日時を先頭に置き、Driveの名前順が実行順になるようにする。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(LOG_DIR, f"{stamp}_{SCRIPT_NAME}.txt")


def _log_header() -> str:
    """ログ先頭に残す実行条件。スクリプトごとに中身が変わる。"""
    return f"metadata={os.path.basename(METADATA_DIR.rstrip(chr(47)))} out={os.path.basename(PROCESSED_DIR.rstrip(chr(47)))}"


class _Tee:
    """書き込みを元のストリームとファイルの両方へ流す。

    切断時に失われないよう毎回flushする。行数は多くないので負荷にならない。
    """

    def __init__(self, stream: Any, fh: Any) -> None:
        self._stream = stream
        self._fh = fh

    def write(self, s: str) -> int:
        n = self._stream.write(s)
        try:
            self._fh.write(s)
            self._fh.flush()
        except Exception:
            pass  # ログが書けなくても本処理は続ける
        return n

    def flush(self) -> None:
        self._stream.flush()
        try:
            self._fh.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
        return bool(getattr(self._stream, "isatty", lambda: False)())

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


class run_logger:
    """標準出力・標準エラーをDrive上のログファイルへ複製する。

    Driveへ直接書く。/content に置くとランタイムが落ちた時点で消え、
    「切断後に読み返す」というこの機能の目的を果たさないため。
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path
        self._fh: Any = None
        self._saved_stdout: Any = None
        self._saved_stderr: Any = None
        self._saved_fd2: Optional[int] = None
        self._pump: Optional[threading.Thread] = None

    @staticmethod
    def _stderr_is_fd2() -> bool:
        """sys.stderr の書き込みが fd 2 に届くか。

        素のPythonでは届くので、fd側で捕捉するなら Tee を掛けると二重になる。
        Jupyter/Colab の sys.stderr は ZMQ 経由で fd 2 を通らないため、
        その場合は Tee が要る。
        """
        try:
            return sys.stderr.fileno() == 2
        except Exception:
            return False

    def _capture_native_stderr(self) -> None:
        r, w = os.pipe()
        self._saved_fd2 = os.dup(2)
        os.dup2(w, 2)
        os.close(w)
        saved = self._saved_fd2
        fh = self._fh

        def pump() -> None:
            with os.fdopen(r, "rb", 0) as rf:
                for line in iter(rf.readline, b""):
                    try:
                        os.write(saved, line)  # 元の出力先へも流す
                    except OSError:
                        pass
                    try:
                        fh.write(line.decode("utf-8", "replace"))
                        fh.flush()
                    except Exception:
                        pass

        self._pump = threading.Thread(target=pump, daemon=True)
        self._pump.start()

    def __enter__(self) -> "run_logger":
        if not LOG_TO_FILE:
            return self
        self.path = self.path or _log_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._fh = open(self.path, "a", encoding=OUTPUT_ENCODING)
        self._fh.write(
            f"\n===== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
            f"{_log_header()} =====\n"
        )
        self._fh.flush()
        stderr_on_fd2 = self._stderr_is_fd2()
        self._saved_stdout, self._saved_stderr = sys.stdout, sys.stderr
        sys.stdout = _Tee(sys.stdout, self._fh)
        native_ok = False
        if LOG_CAPTURE_NATIVE_STDERR:
            try:
                self._capture_native_stderr()
                native_ok = True
            except Exception as e:
                print(f"[warn] native stderr capture disabled: {type(e).__name__}: {e}")
        # fd側で拾えていて、かつ sys.stderr がそこへ流れるなら Tee は不要。
        # 掛けると同じ行が2度記録される。
        if not (native_ok and stderr_on_fd2):
            sys.stderr = _Tee(sys.stderr, self._fh)
        print(f"[info] log: {self.path}")
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self._fh is None:
            return False
        if exc is not None:
            # 中断・異常終了の理由を残す。ここが本機能の主目的である。
            try:
                self._fh.write(
                    "\n[error] " + "".join(traceback.format_exception(exc_type, exc, tb))
                )
                self._fh.flush()
            except Exception:
                pass
        if self._saved_fd2 is not None:
            os.dup2(self._saved_fd2, 2)  # パイプの書き端が閉じ、pumpがEOFで抜ける
            os.close(self._saved_fd2)
            self._saved_fd2 = None
            if self._pump is not None:
                self._pump.join(timeout=5)
        sys.stdout, sys.stderr = self._saved_stdout, self._saved_stderr
        try:
            self._fh.write(f"===== end {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            self._fh.close()
        except Exception:
            pass
        self._fh = None
        return False


def _with_run_log(fn: Any) -> Any:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with run_logger():
            return fn(*args, **kwargs)

    return wrapper


@_with_run_log
def main() -> None:
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    targets = load_targets()
    if MAX_DOCUMENTS is not None and MAX_DOCUMENTS > 0:
        targets = targets[:MAX_DOCUMENTS]

    for meta in targets:
        meta["_day"] = _date_to_compact(str(meta.get("disclosure_date", "")))
    targets.sort(key=lambda m: (m["_day"], str(m.get("code", "")), str(m.get("title", ""))))

    days = sorted({m["_day"] for m in targets})
    processed_ids, processed_keys = load_processed(days)
    print(f"[info] already processed: {len(processed_ids)} ids / {len(processed_keys)} keys")

    pdf_root = _resolve_pdf_root()
    if not pdf_root:
        raise FileNotFoundError(f"no pdf root found among: {list(RAW_PDF_ROOT_DIRS)}")
    by_date = _build_pdf_index(pdf_root)
    print(f"[info] pdf root={pdf_root} files={sum(len(v) for v in by_date.values())}")

    handles: Dict[str, Any] = {}
    csv_handles: Dict[str, Any] = {}
    csv_writers: Dict[str, Any] = {}
    counters: Counter = Counter()
    layout_counter: Counter = Counter()
    started = time.time()
    total = len(targets)

    try:
        for n, meta in enumerate(targets, 1):
            day = meta["_day"]
            document_id = str(meta.get("document_id", "") or "")
            source_key = _source_key(meta)
            # document_id は PDF を開くまで確定しないことがあるため、再開キーでも判定する
            if (document_id and document_id in processed_ids) or source_key in processed_keys:
                counters["skipped_done"] += 1
                continue

            if day not in handles:
                handles[day] = open(_output_path_for_day(day), "a", encoding=OUTPUT_ENCODING)
                if WRITE_CSV:
                    csv_handles[day], csv_writers[day] = open_csv_appender(_csv_path_for_day(day))

            pdf_path = _resolve_pdf_path(meta, by_date, day)
            if not pdf_path:
                record = {
                    "document_id": document_id
                    or f"{day}_{meta.get('code', '')}_{_sha256_of_text(source_key)}",
                    "disclosure_date": str(meta.get("disclosure_date", "")),
                    "disclosure_time": str(meta.get("disclosure_time", "")),
                    "code": str(meta.get("code", "")),
                    "company_name": str(meta.get("company_name", "")),
                    "title": str(meta.get("title", "")),
                    "source_type": str(meta.get("source_type", ""))
                    or classify_source_type(str(meta.get("title", ""))),
                    "jpx_sector_17": str(meta.get("jpx_sector_17", "")),
                    "document_url": str(meta.get("document_url", "")),
                    "pdf_sha256": str(meta.get("pdf_sha256", "")),
                    "page_count": 0,
                    "char_count": 0,
                    "pdf_layout_type": "unknown",
                    "text": "",
                    "blocks": [],
                    "status": "failed",
                    "error": "pdf_not_found",
                }
                counters["failed"] += 1
            else:
                try:
                    record = process_one_pdf(meta, pdf_path)
                    counters[record["status"]] += 1
                    layout_counter[record["pdf_layout_type"]] += 1
                except Exception as e:
                    record = {
                        "document_id": document_id
                        or f"{day}_{meta.get('code', '')}_{_sha256_of_text(source_key)}",
                        "disclosure_date": str(meta.get("disclosure_date", "")),
                        "disclosure_time": str(meta.get("disclosure_time", "")),
                        "code": str(meta.get("code", "")),
                        "company_name": str(meta.get("company_name", "")),
                        "title": str(meta.get("title", "")),
                        "source_type": str(meta.get("source_type", ""))
                        or classify_source_type(str(meta.get("title", ""))),
                        "jpx_sector_17": str(meta.get("jpx_sector_17", "")),
                        "document_url": str(meta.get("document_url", "")),
                        "pdf_sha256": str(meta.get("pdf_sha256", "")),
                        "page_count": 0,
                        "char_count": 0,
                        "pdf_layout_type": "unknown",
                        "text": "",
                        "blocks": [],
                        "status": "failed",
                        "error": f"{type(e).__name__}: {e}",
                    }
                    counters["failed"] += 1
                    traceback.print_exc()

            # 1件ごとに追記して flush する。全件終了後にまとめて書き出さない（02§8.3）。
            handles[day].write(json.dumps(record, ensure_ascii=False) + "\n")
            handles[day].flush()
            if WRITE_CSV:
                csv_writers[day].writerow(record_to_csv_row(record))
                csv_handles[day].flush()
            processed_ids.add(record["document_id"])
            processed_keys.add(source_key)

            elapsed = time.time() - started
            done = n
            eta = (elapsed / done) * (total - done) if done else 0.0
            print(
                f"[{n}/{total}] {record['document_id']} status={record['status']} "
                f"layout={record['pdf_layout_type']} chars={record['char_count']} "
                f"blocks={len(record['blocks'])} eta={eta / 60:.1f}min"
            )
    finally:
        for f in list(handles.values()) + list(csv_handles.values()):
            f.close()

    print("\n[done] preprocessing finished")
    print(f"[done] status  : {dict(counters)}")
    print(f"[done] layouts : {dict(layout_counter)}")
    print(f"[done] elapsed : {(time.time() - started) / 60:.1f} min")
    for day in days:
        path = _output_path_for_day(day)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                print(f"[done] {path}: {sum(1 for _ in f)} lines")
        csv_path = _csv_path_for_day(day)
        if WRITE_CSV and os.path.exists(csv_path):
            print(f"[done] {csv_path}")


if __name__ == "__main__":
    main()
