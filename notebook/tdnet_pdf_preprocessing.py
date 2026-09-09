# -*- coding: utf-8 -*-

# ==========================================
# TDnet PDF 前処理パイプライン（ペライチ）
# Colab 1セル貼り付け実行OK
#
# 機能 (MVP):
#   - 日次の開示メタデータCSVを読み込み、対象PDFを解決
#   - SHA256/document_id採番
#   - ページ単位レイアウト判定
#   - テキストブロック抽出 (PyMuPDF)
#   - 表抽出 (pdfplumber)
#   - normalized.md / document_blocks.jsonl / document_tables.jsonl 生成
#   - candidate_evidence_spans.jsonl 生成
#   - processing_report.json 生成
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
import traceback
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def _ensure_dependency(module_name: str, pip_name: Optional[str] = None) -> None:
    try:
        __import__(module_name)
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name or module_name])


_ensure_dependency("pandas")
_ensure_dependency("fitz", "pymupdf")
_ensure_dependency("pdfplumber")

import fitz  # type: ignore
import pandas as pd
import pdfplumber  # type: ignore


# -----------------------------
# 0) 設定（ここだけ編集すればOK）
# -----------------------------
ROOT_DIR = "/content/drive/MyDrive/git/prop_candidates/"
METADATA_CLASSIFIED_DIR = ROOT_DIR + "data/processed/tdnet_metadata_classified/"
RAW_PDF_ROOT_DIR = ROOT_DIR + "data/raw/tdnet_pdfs/"
OUTPUT_ROOT_DIR = ROOT_DIR + "data/processed/tdnet_pdf_preprocessed/"
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
SCRIPT_NAME = "tdnet_pdf_preprocessing"

TARGET_ONLY_REAL_ESTATE_CANDIDATES = False
MAX_DOCUMENTS: Optional[int] = None
START_DATE = ""  # YYYY-MM-DD または YYYYMMDD。空なら全期間
END_DATE = ""  # YYYY-MM-DD または YYYYMMDD。空なら全期間

# evidence span 前後ブロック
EVIDENCE_CONTEXT_WINDOW = 1
MAX_EVIDENCE_CHAR_COUNT = 2800

# layout判定閾値（初期値）
SCAN_TEXT_CHAR_THRESHOLD = 40
SCAN_IMAGE_AREA_THRESHOLD = 0.35
SLIDE_ASPECT_THRESHOLD = 1.2
DOC_TEXT_CHAR_THRESHOLD = 250

EVIDENCE_KEYWORDS: Sequence[str] = [
    "譲渡資産の内容",
    "取得資産の内容",
    "譲渡の理由",
    "取得の理由",
    "譲渡価額",
    "取得価額",
    "帳簿価額",
    "譲渡益",
    "譲渡損",
    "固定資産売却益",
    "所在地",
    "土地",
    "建物",
    "構築物",
    "信託受益権",
    "販売用不動産",
    "賃貸用不動産",
    "投資不動産",
    "セール・アンド・リースバック",
    "所有権移転",
    "物件引渡",
    "契約締結日",
]


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    txt = unicodedata.normalize("NFKC", str(value))
    txt = txt.replace("\u3000", " ")
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


def _build_document_id(disclosure_date: str, issuer_code: str, sha256_hex: str) -> str:
    yyyymmdd = _date_to_compact(disclosure_date)
    code = _safe_filename(str(issuer_code or "unknown_code"))
    return f"{yyyymmdd}_{code}_{sha256_hex[:8]}"


def _date_range_inclusive(start_date: str, end_date: str) -> List[str]:
    start_txt = _date_to_compact(start_date)
    end_txt = _date_to_compact(end_date)
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


def _metadata_csv_path_for_day(yyyymmdd: str) -> str:
    return os.path.join(
        METADATA_CLASSIFIED_DIR,
        f"tdnet_metadata_{yyyymmdd}_real_estate_classified.csv",
    )


def _discover_available_metadata_days(metadata_dir: str) -> List[str]:
    if not os.path.exists(metadata_dir):
        return []
    pattern = re.compile(r"^tdnet_metadata_(\d{8})_real_estate_classified\.csv$")
    days: List[str] = []
    for name in os.listdir(metadata_dir):
        m = pattern.match(name)
        if m:
            days.append(m.group(1))
    return sorted(set(days))


def _build_block_id(document_id: str, page_number: int, block_order: int) -> str:
    return f"{document_id}_p{page_number:03d}_b{block_order:03d}"


def _build_table_id(document_id: str, page_number: int, table_order: int) -> str:
    return f"{document_id}_p{page_number:03d}_t{table_order:03d}"


def _build_evidence_id(document_id: str, evidence_order: int) -> str:
    return f"{document_id}_ev{evidence_order:03d}"


def _iter_pdf_files(root_dir: str) -> Iterable[str]:
    if not os.path.exists(root_dir):
        return []
    paths: List[str] = []
    for dp, _, files in os.walk(root_dir):
        for name in files:
            if name.lower().endswith(".pdf"):
                paths.append(os.path.join(dp, name))
    return paths


def _extract_compact_date_from_path(path: str) -> str:
    m = re.search(r"(\d{8})", path or "")
    return m.group(1) if m else ""


@dataclass
class PdfIndex:
    all_paths: List[str]
    by_basename: Dict[str, List[str]]
    by_date: Dict[str, List[str]]


def build_pdf_index(root_dir: str) -> PdfIndex:
    all_paths = list(_iter_pdf_files(root_dir))
    by_basename: Dict[str, List[str]] = defaultdict(list)
    by_date: Dict[str, List[str]] = defaultdict(list)
    for p in all_paths:
        bn = os.path.basename(p)
        by_basename[bn].append(p)
        m = re.search(r"(\d{8})", p)
        if m:
            by_date[m.group(1)].append(p)
    return PdfIndex(all_paths=all_paths, by_basename=by_basename, by_date=by_date)


def _resolve_pdf_path(row: pd.Series, idx: PdfIndex, target_date: str) -> Optional[str]:
    scoped = idx.by_date.get(target_date, [])
    scoped_set = set(scoped)
    if not scoped:
        return None

    # 1) 明示パス列
    for col in ("local_pdf_path", "pdf_local_path", "pdf_path"):
        v = str(row.get(col, "") or "").strip()
        if not v:
            continue
        if os.path.exists(v):
            if _extract_compact_date_from_path(v) == target_date:
                return v
            continue
        candidate = os.path.join(ROOT_DIR, v.lstrip("/"))
        if os.path.exists(candidate):
            if _extract_compact_date_from_path(candidate) == target_date:
                return candidate
            continue

    # 2) URL basename一致（日付スコープ内のみ）
    document_url = str(row.get("document_url", "") or "").strip()
    if document_url:
        bn = os.path.basename(document_url)
        if bn in idx.by_basename and idx.by_basename[bn]:
            for p in idx.by_basename[bn]:
                if p in scoped_set:
                    return p

    # 3) date + code + disclosure_number を優先探索（日付スコープ内のみ）
    code = str(row.get("code", "") or "").strip()
    disclosure_number = str(row.get("disclosure_number", "") or "").strip()
    if disclosure_number:
        for p in scoped:
            bn = os.path.basename(p)
            if disclosure_number in bn and (not code or f"_{code}_" in bn or bn.startswith(f"{target_date}_{code}_")):
                return p

    # 4) date + code だけで探索（日付スコープ内のみ）
    if code:
        for p in scoped:
            bn = os.path.basename(p)
            if f"_{code}_" in bn or bn.startswith(f"{target_date}_{code}_"):
                return p
    return None


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
    mojibake_penalty = 0.2 if "\ufffd" in t else 0.0
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


def _compute_table_quality(rows: List[List[str]]) -> float:
    if not rows:
        return 0.1
    cell_count = sum(len(r) for r in rows if r)
    filled_count = sum(1 for r in rows for c in r if _normalize_text(c))
    if cell_count == 0:
        return 0.1
    ratio = filled_count / cell_count
    return max(0.0, min(1.0, round(0.25 + 0.75 * ratio, 4)))


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


def _score_document_quality(
    *,
    page_count: int,
    text_char_count: int,
    block_count: int,
    table_count: int,
    scanned_pages: int,
) -> str:
    if page_count <= 0 or text_char_count <= 0:
        return "low"
    chars_per_page = text_char_count / max(1, page_count)
    scanned_ratio = scanned_pages / max(1, page_count)
    if chars_per_page >= 800 and block_count >= page_count * 5 and scanned_ratio <= 0.2:
        return "high"
    if chars_per_page >= 250 and scanned_ratio <= 0.6 and (table_count > 0 or block_count > page_count * 2):
        return "medium"
    return "low"


def _write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding=OUTPUT_ENCODING) as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _is_repeated_header_footer(text_norm: str, page_count: int, freq: int, y0: float, y1: float, page_height: float) -> str:
    if page_count < 2 or freq < 2 or not text_norm:
        return ""
    top_th = page_height * 0.12
    bottom_th = page_height * 0.88
    if y1 <= top_th:
        return "header"
    if y0 >= bottom_th:
        return "footer"
    return ""


def _build_evidence_type(keyword_hits: Sequence[str]) -> str:
    joined = "".join(keyword_hits)
    if any(k in joined for k in ("譲渡の理由", "取得の理由")):
        return "transaction_reason"
    if any(k in joined for k in ("譲渡価額", "取得価額", "帳簿価額", "譲渡益", "譲渡損", "所在地", "土地", "建物")):
        return "asset_transaction_detail"
    if any(k in joined for k in ("セール・アンド・リースバック", "信託受益権", "販売用不動産")):
        return "transaction_scheme"
    return "candidate"


def _build_normalized_markdown(
    *,
    metadata: Dict[str, Any],
    pdf_layout_type: str,
    page_count: int,
    page_texts: Dict[int, List[str]],
    page_tables: Dict[int, List[str]],
) -> str:
    lines: List[str] = []
    lines.append("---")
    lines.append(f"document_id: {metadata['document_id']}")
    lines.append(f"issuer_code: {metadata.get('issuer_code', '')}")
    lines.append(f"issuer_name: {metadata.get('issuer_name', '')}")
    lines.append(f"disclosure_date: {metadata.get('disclosure_date', '')}")
    lines.append(f"title: {metadata.get('title', '')}")
    lines.append(f"pdf_layout_type: {pdf_layout_type}")
    lines.append(f"page_count: {page_count}")
    lines.append("---")
    lines.append("")

    for p in range(1, page_count + 1):
        lines.append(f"# Page {p}")
        lines.append("")
        for text in page_texts.get(p, []):
            lines.append(text)
            lines.append("")
        tables = page_tables.get(p, [])
        if tables:
            lines.append("## Tables")
            lines.append("")
            for t in tables:
                lines.append(t)
                lines.append("")
    return "\n".join(lines).strip() + "\n"


def process_one_pdf(
    row: pd.Series,
    pdf_path: str,
    out_root_dir: str,
) -> Dict[str, Any]:
    issuer_code = str(row.get("code", "") or "").strip()
    issuer_name = str(row.get("company_name", "") or "").strip()
    disclosure_date = str(row.get("disclosure_date", "") or "").strip()
    title = str(row.get("title", "") or "").strip()
    document_url = str(row.get("document_url", "") or "").strip()

    source_id = str(row.get("source_id", "") or "").strip()
    if not source_id:
        source_id = str(row.get("disclosure_number", "") or "").strip() or document_url or os.path.basename(pdf_path)

    sha256_hex = _compute_sha256(pdf_path)
    document_id = _build_document_id(disclosure_date=disclosure_date, issuer_code=issuer_code, sha256_hex=sha256_hex)
    doc_dir = os.path.join(out_root_dir, _date_to_compact(disclosure_date), "documents", document_id)
    os.makedirs(doc_dir, exist_ok=True)

    raw_copy_path = os.path.join(doc_dir, "raw.pdf")
    if not os.path.exists(raw_copy_path):
        with open(pdf_path, "rb") as src, open(raw_copy_path, "wb") as dst:
            dst.write(src.read())

    errors: List[str] = []
    blocks: List[Dict[str, Any]] = []
    tables: List[Dict[str, Any]] = []
    page_layouts: List[str] = []
    page_texts: Dict[int, List[str]] = defaultdict(list)
    page_tables_md: Dict[int, List[str]] = defaultdict(list)
    text_char_total = 0

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise RuntimeError(f"failed to open pdf: {e}") from e

    try:
        with pdfplumber.open(pdf_path) as plumber_doc:
            page_count = len(doc)
            normalized_counter: Counter[str] = Counter()
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
                text_blocks = sorted(text_blocks, key=lambda x: (round(float(x[1]), 1), round(float(x[0]), 1)))
                extracted_text = page.get_text("text") or ""
                text_char_count = len(_normalize_text(extracted_text))
                text_char_total += text_char_count

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
                            if t and any(any(_normalize_text(c) for c in row_cells if c is not None) for row_cells in t):
                                table_rows_list.append(
                                    [[_normalize_text(c) for c in (r or [])] for r in t if r is not None]
                                )
                    except Exception as te:
                        errors.append(f"table_extract_error_page_{page_number}: {te}")
                detected_table_count = len(table_rows_list)

                avg_text_block_length = 0.0
                if text_blocks:
                    avg_text_block_length = sum(len(_normalize_text(b[4])) for b in text_blocks) / len(text_blocks)

                stats = {
                    "page_width": round(page_width, 2),
                    "page_height": round(page_height, 2),
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
                    block_id = _build_block_id(document_id, page_number, j)
                    rec = {
                        "block_id": block_id,
                        "document_id": document_id,
                        "page_number": page_number,
                        "page_layout_type": page_layout_type,
                        "block_order": j,
                        "block_type": _guess_block_type(text_norm, page_number, j),
                        "text": text_norm,
                        "normalized_text": _normalize_for_match(text_norm),
                        "char_count": len(text_norm),
                        "bbox": [round(float(x0), 2), round(float(y0), 2), round(float(x1), 2), round(float(y1), 2)],
                        "extraction_method": "pymupdf_text",
                        "quality_score": _compute_block_quality(text_norm, "pymupdf_text"),
                    }
                    blocks.append(rec)
                    page_texts[page_number].append(text_norm)
                    normalized_counter[rec["normalized_text"]] += 1
                    block_positions.append((len(blocks) - 1, page_number, float(y0), float(y1), page_height))

                for t_idx, rows in enumerate(table_rows_list, 1):
                    table_id = _build_table_id(document_id, page_number, t_idx)
                    md_table = _table_to_markdown(rows)
                    trec = {
                        "table_id": table_id,
                        "document_id": document_id,
                        "page_number": page_number,
                        "page_layout_type": page_layout_type,
                        "table_order": t_idx,
                        "markdown_table": md_table,
                        "raw_cells_json": rows,
                        "extraction_method": "pdfplumber_table",
                        "quality_score": _compute_table_quality(rows),
                    }
                    tables.append(trec)
                    if md_table:
                        page_tables_md[page_number].append(md_table)

            # header/footerタグ付け（同一文言の繰り返し）
            for block_idx, page_number, y0, y1, page_height in block_positions:
                b = blocks[block_idx]
                repeated_type = _is_repeated_header_footer(
                    text_norm=b["normalized_text"],
                    page_count=page_count,
                    freq=normalized_counter.get(b["normalized_text"], 0),
                    y0=y0,
                    y1=y1,
                    page_height=page_height,
                )
                if repeated_type:
                    b["block_type"] = repeated_type
                    b["quality_score"] = min(0.4, b["quality_score"])

            pdf_layout_type = _infer_pdf_layout_type(page_layouts)
            scanned_pages = sum(1 for x in page_layouts if x == "scanned_or_image")
            doc_quality = _score_document_quality(
                page_count=page_count,
                text_char_count=text_char_total,
                block_count=len(blocks),
                table_count=len(tables),
                scanned_pages=scanned_pages,
            )

            # candidate evidence spans
            evidence_rows: List[Dict[str, Any]] = []
            block_id_to_idx = {b["block_id"]: i for i, b in enumerate(blocks)}
            keyword_norms = [_normalize_for_match(k) for k in EVIDENCE_KEYWORDS]
            hit_block_ids: List[str] = []
            for b in blocks:
                ntext = b["normalized_text"]
                if any(k in ntext for k in keyword_norms):
                    hit_block_ids.append(b["block_id"])

            # テーブル内キーワードヒット
            page_hit_tables: Dict[int, List[str]] = defaultdict(list)
            for t in tables:
                t_norm = _normalize_for_match(t["markdown_table"])
                hits = [kw for kw, kn in zip(EVIDENCE_KEYWORDS, keyword_norms) if kn and kn in t_norm]
                if hits:
                    page_hit_tables[int(t["page_number"])].append(t["table_id"])

            seen_signature: set[Tuple[int, Tuple[str, ...]]] = set()
            ev_order = 1
            for hit_block_id in hit_block_ids:
                hit_idx = block_id_to_idx[hit_block_id]
                hit_block = blocks[hit_idx]
                page_num = int(hit_block["page_number"])
                order = int(hit_block["block_order"])

                # 前後ブロックをコンテキストに含める
                context_ids = [
                    b["block_id"]
                    for b in blocks
                    if int(b["page_number"]) == page_num and abs(int(b["block_order"]) - order) <= EVIDENCE_CONTEXT_WINDOW
                ]
                nearby_table_ids = [tid for tid in page_hit_tables.get(page_num, [])]
                span_block_ids = context_ids + nearby_table_ids

                signature = (page_num, tuple(sorted(span_block_ids)))
                if signature in seen_signature:
                    continue
                seen_signature.add(signature)

                span_text_parts: List[str] = []
                keyword_hits: List[str] = []
                for bid in context_ids:
                    b = blocks[block_id_to_idx[bid]]
                    span_text_parts.append(b["text"])
                    ntext = b["normalized_text"]
                    keyword_hits.extend([kw for kw, kn in zip(EVIDENCE_KEYWORDS, keyword_norms) if kn and kn in ntext])
                for tid in nearby_table_ids:
                    t = next((x for x in tables if x["table_id"] == tid), None)
                    if t and t["markdown_table"]:
                        span_text_parts.append(t["markdown_table"])
                        t_norm = _normalize_for_match(t["markdown_table"])
                        keyword_hits.extend([kw for kw, kn in zip(EVIDENCE_KEYWORDS, keyword_norms) if kn and kn in t_norm])

                if not span_text_parts:
                    continue
                span_text = "\n\n".join(span_text_parts).strip()
                if len(span_text) > MAX_EVIDENCE_CHAR_COUNT:
                    span_text = span_text[:MAX_EVIDENCE_CHAR_COUNT] + "\n...[truncated]"
                keyword_hits = sorted(set(keyword_hits))
                ev = {
                    "evidence_id": _build_evidence_id(document_id, ev_order),
                    "document_id": document_id,
                    "page_numbers": [page_num],
                    "block_ids": span_block_ids,
                    "evidence_type": _build_evidence_type(keyword_hits),
                    "keyword_hits": keyword_hits,
                    "text": span_text,
                    "char_count": len(span_text),
                    "quality_score": round(float(hit_block.get("quality_score", 0.5)), 4),
                }
                evidence_rows.append(ev)
                ev_order += 1

            metadata_obj = {
                "document_id": document_id,
                "source_id": source_id,
                "issuer_code": issuer_code,
                "issuer_name": issuer_name,
                "disclosure_date": disclosure_date,
                "disclosure_time": str(row.get("disclosure_time", "") or ""),
                "title": title,
                "document_url": document_url,
                "local_pdf_path": pdf_path,
                "sha256_hash": sha256_hex,
            }

            md_text = _build_normalized_markdown(
                metadata=metadata_obj,
                pdf_layout_type=pdf_layout_type,
                page_count=page_count,
                page_texts=page_texts,
                page_tables=page_tables_md,
            )
            with open(os.path.join(doc_dir, "normalized.md"), "w", encoding=OUTPUT_ENCODING) as f:
                f.write(md_text)
            _write_jsonl(os.path.join(doc_dir, "document_blocks.jsonl"), blocks)
            _write_jsonl(os.path.join(doc_dir, "document_tables.jsonl"), tables)
            _write_jsonl(os.path.join(doc_dir, "candidate_evidence_spans.jsonl"), evidence_rows)

            evidence_package = {
                "document_metadata": {
                    "document_id": document_id,
                    "issuer_code": issuer_code,
                    "issuer_name": issuer_name,
                    "title": title,
                    "disclosure_date": disclosure_date,
                    "pdf_layout_type": pdf_layout_type,
                },
                "candidate_evidence_spans": evidence_rows,
            }
            with open(os.path.join(doc_dir, "evidence_package.json"), "w", encoding=OUTPUT_ENCODING) as f:
                json.dump(evidence_package, f, ensure_ascii=False, indent=2)

            report = {
                "document_id": document_id,
                "source_pdf_path": pdf_path,
                "sha256_hash": sha256_hex,
                "page_count": page_count,
                "pdf_layout_type": pdf_layout_type,
                "page_layout_summary": dict(Counter(page_layouts)),
                "text_char_count": text_char_total,
                "block_count": len(blocks),
                "table_count": len(tables),
                "evidence_span_count": len(evidence_rows),
                "document_text_extraction_quality": doc_quality,
                "used_ocr": False,
                "used_vision": False,
                "ocr_candidate": bool(doc_quality == "low"),
                "processing_status": "success" if not errors else "success_with_warnings",
                "errors": errors,
                "processed_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            with open(os.path.join(doc_dir, "processing_report.json"), "w", encoding=OUTPUT_ENCODING) as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            return {
                "document_id": document_id,
                "status": "success",
                "disclosure_date": disclosure_date,
                "issuer_code": issuer_code,
                "title": title,
                "pdf_layout_type": pdf_layout_type,
                "evidence_span_count": len(evidence_rows),
                "ocr_candidate": bool(doc_quality == "low"),
                "output_dir": doc_dir,
            }
    finally:
        doc.close()


def _log_path() -> str:
    """<LOG_DIR>/<日時>_<スクリプト名>.txt

    日時を先頭に置き、Driveの名前順が実行順になるようにする。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(LOG_DIR, f"{stamp}_{SCRIPT_NAME}.txt")


def _log_header() -> str:
    """ログ先頭に残す実行条件。スクリプトごとに中身が変わる。"""
    return f"pdf_root={RAW_PDF_ROOT_DIR} out={OUTPUT_ROOT_DIR}"


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
    if not os.path.exists(METADATA_CLASSIFIED_DIR):
        raise FileNotFoundError(f"metadata dir not found: {METADATA_CLASSIFIED_DIR}")
    if not os.path.exists(RAW_PDF_ROOT_DIR):
        raise FileNotFoundError(f"raw pdf root dir not found: {RAW_PDF_ROOT_DIR}")

    os.makedirs(OUTPUT_ROOT_DIR, exist_ok=True)
    if START_DATE or END_DATE:
        if not (START_DATE and END_DATE):
            raise ValueError("If using date range, set both START_DATE and END_DATE")
        target_days = _date_range_inclusive(START_DATE, END_DATE)
    else:
        target_days = _discover_available_metadata_days(METADATA_CLASSIFIED_DIR)
        if not target_days:
            raise RuntimeError(f"no daily metadata files found under: {METADATA_CLASSIFIED_DIR}")

    idx = build_pdf_index(RAW_PDF_ROOT_DIR)
    print(f"[info] metadata days : {len(target_days)}")
    print(f"[info] indexed pdfs : {len(idx.all_paths)}")

    all_summary_rows: List[Dict[str, Any]] = []
    all_failed_rows: List[Dict[str, Any]] = []
    all_layout_counter: Counter[str] = Counter()
    all_evidence_total = 0
    all_ocr_candidate_count = 0

    remaining_docs = MAX_DOCUMENTS if (MAX_DOCUMENTS is not None and MAX_DOCUMENTS > 0) else None
    for day in target_days:
        metadata_csv = _metadata_csv_path_for_day(day)
        if not os.path.exists(metadata_csv):
            print(f"[warn] skip day={day} metadata not found: {metadata_csv}")
            continue

        day_df = pd.read_csv(metadata_csv, dtype=str).fillna("")
        if "disclosure_date" not in day_df.columns:
            print(f"[warn] skip day={day} missing disclosure_date column: {metadata_csv}")
            continue
        day_df["disclosure_date_compact"] = day_df["disclosure_date"].apply(_date_to_compact)
        day_df = day_df[day_df["disclosure_date_compact"] == day].copy()
        if TARGET_ONLY_REAL_ESTATE_CANDIDATES and "is_real_estate_transaction_candidate" in day_df.columns:
            day_df = day_df[day_df["is_real_estate_transaction_candidate"].astype(str).str.lower().isin(["true", "1"])].copy()
        if remaining_docs is not None:
            if remaining_docs <= 0:
                print("[info] reached MAX_DOCUMENTS. stop further days.")
                break
            day_df = day_df.head(remaining_docs).copy()
            remaining_docs -= len(day_df)

        if day_df.empty:
            print(f"[info] skip day={day} no rows after filters")
            continue

        day_out_dir = os.path.join(OUTPUT_ROOT_DIR, day)
        os.makedirs(day_out_dir, exist_ok=True)
        day_summary_rows: List[Dict[str, Any]] = []
        day_failed_rows: List[Dict[str, Any]] = []
        day_layout_counter: Counter[str] = Counter()
        day_evidence_total = 0
        day_ocr_candidate_count = 0

        print(f"\n[info] === processing day={day} rows={len(day_df)} ===")
        for i, (_, row) in enumerate(day_df.iterrows(), 1):
            pdf_path = _resolve_pdf_path(row, idx, target_date=day)
            if not pdf_path:
                day_failed_rows.append(
                    {
                        "source_id": str(row.get("disclosure_number", "") or row.get("document_url", "") or f"row_{i}"),
                        "error": "pdf_not_found_in_target_date",
                        "target_date": day,
                        "title": str(row.get("title", "")),
                    }
                )
                print(f"[warn] {i}/{len(day_df)} pdf not found in day={day}: {row.get('title', '')}")
                continue

            resolved_date = _extract_compact_date_from_path(pdf_path)
            if resolved_date != day:
                day_failed_rows.append(
                    {
                        "source_id": str(row.get("disclosure_number", "") or row.get("document_url", "") or f"row_{i}"),
                        "error": "date_mismatch_between_metadata_and_pdf_path",
                        "target_date": day,
                        "resolved_pdf_date": resolved_date,
                        "resolved_pdf_path": pdf_path,
                        "title": str(row.get("title", "")),
                    }
                )
                print(f"[warn] {i}/{len(day_df)} date mismatch day={day} resolved={resolved_date}")
                continue

            try:
                result = process_one_pdf(row=row, pdf_path=pdf_path, out_root_dir=OUTPUT_ROOT_DIR)
                day_summary_rows.append(result)
                day_layout_counter[result["pdf_layout_type"]] += 1
                day_evidence_total += int(result["evidence_span_count"])
                if result["ocr_candidate"]:
                    day_ocr_candidate_count += 1
                print(
                    f"[done] {i}/{len(day_df)} {result['document_id']} "
                    f"layout={result['pdf_layout_type']} evidence={result['evidence_span_count']}"
                )
            except Exception as e:
                err_text = f"{type(e).__name__}: {e}"
                day_failed_rows.append(
                    {
                        "source_id": str(row.get("disclosure_number", "") or row.get("document_url", "") or f"row_{i}"),
                        "error": err_text,
                        "target_date": day,
                        "title": str(row.get("title", "")),
                    }
                )
                print(f"[error] {i}/{len(day_df)} failed: {err_text}")
                traceback.print_exc()

        day_summary_path = os.path.join(day_out_dir, "processing_summary.csv")
        day_failed_path = os.path.join(day_out_dir, "processing_failed.csv")
        pd.DataFrame(day_summary_rows).to_csv(day_summary_path, index=False, encoding="utf-8-sig")
        pd.DataFrame(day_failed_rows).to_csv(day_failed_path, index=False, encoding="utf-8-sig")
        day_report = {
            "target_date": day,
            "processed_pdf_count": len(day_summary_rows),
            "success_count": len(day_summary_rows),
            "failed_count": len(day_failed_rows),
            "layout_type_counts": dict(day_layout_counter),
            "evidence_span_total": day_evidence_total,
            "ocr_candidate_count": day_ocr_candidate_count,
            "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "summary_csv": day_summary_path,
            "failed_csv": day_failed_path,
        }
        with open(os.path.join(day_out_dir, "daily_processing_report.json"), "w", encoding=OUTPUT_ENCODING) as f:
            json.dump(day_report, f, ensure_ascii=False, indent=2)

        all_summary_rows.extend(day_summary_rows)
        all_failed_rows.extend(day_failed_rows)
        all_layout_counter.update(day_layout_counter)
        all_evidence_total += day_evidence_total
        all_ocr_candidate_count += day_ocr_candidate_count

    summary_path = os.path.join(OUTPUT_ROOT_DIR, "processing_summary_all.csv")
    failed_path = os.path.join(OUTPUT_ROOT_DIR, "processing_failed_all.csv")
    pd.DataFrame(all_summary_rows).to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(all_failed_rows).to_csv(failed_path, index=False, encoding="utf-8-sig")

    aggregate_report = {
        "processed_pdf_count": len(all_summary_rows),
        "success_count": len(all_summary_rows),
        "failed_count": len(all_failed_rows),
        "layout_type_counts": dict(all_layout_counter),
        "evidence_span_total": all_evidence_total,
        "ocr_candidate_count": all_ocr_candidate_count,
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "summary_csv": summary_path,
        "failed_csv": failed_path,
    }
    with open(os.path.join(OUTPUT_ROOT_DIR, "processing_report_all.json"), "w", encoding=OUTPUT_ENCODING) as f:
        json.dump(aggregate_report, f, ensure_ascii=False, indent=2)

    print("\n[done] preprocessing finished")
    print(f"[done] processed={len(all_summary_rows)} failed={len(all_failed_rows)}")
    print(f"[done] layout_counts={dict(all_layout_counter)}")
    print(f"[done] evidence_total={all_evidence_total} ocr_candidate_count={all_ocr_candidate_count}")
    print(f"[done] summary: {summary_path}")
    print(f"[done] failed : {failed_path}")


if __name__ == "__main__":
    main()
