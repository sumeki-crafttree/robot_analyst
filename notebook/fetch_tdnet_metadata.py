# -*- coding: utf-8 -*-

# ==========================================
# TDnet 日次メタデータ取得スクリプト
# Colab 1セル貼り付け実行OK
#
# 機能:
#   - 指定日(YYYY-MM-DD)のTDnet開示メタデータを全件取得
#   - 100件超の場合も 001, 002, ... ページを自動巡回
#   - DataFrameを表示し、CSV保存
# ==========================================

import functools
import os
import re
import threading
import time
import subprocess
import sys
import hashlib
import traceback
from datetime import date, datetime, timedelta
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse


def _ensure_dependency(module_name: str, pip_name: Optional[str] = None) -> None:
    try:
        __import__(module_name)
    except Exception:
        target = pip_name or module_name
        subprocess.check_call([sys.executable, "-m", "pip", "install", target])


_ensure_dependency("requests")
_ensure_dependency("bs4", "beautifulsoup4")
_ensure_dependency("pandas")
_ensure_dependency("xlrd")  # JPXマスタ（.xls）を読むため

import pandas as pd
import requests
from bs4 import BeautifulSoup


# -----------------------------
# 0) 設定（ここだけ編集すればOK）
# -----------------------------
# "single" なら TARGET_DATE、"range" なら START_DATE/END_DATE を使用
# single | range | annotate
#   annotate は既存の日次CSVを読み直して分類5項目を付け直すだけ。
#   TDnetにも取りに行かず、PDFにも触らない。分類ロジックを変えた時に使う。
FETCH_MODE = "single"
TARGET_DATE = "2026-05-20"  # YYYY-MM-DD
START_DATE = "2026-05-19"  # YYYY-MM-DD
END_DATE = "2026-05-20"  # YYYY-MM-DD

ROOT_DIR = "/content/drive/MyDrive/git/prop_candidates/"
ORIGINAL_DIR = ROOT_DIR + "data/original/"
OUTPUT_CSV = ORIGINAL_DIR + f"tdnet_metadata_{TARGET_DATE.replace('-', '')}.csv"
RAW_DIR = ROOT_DIR + "data/raw/"
MASTER_DIR = ROOT_DIR + "data/master/"
# 銘柄コードで突合して業種・市場区分を確定させる（02§3.1）
JPX_LISTED_XLS = MASTER_DIR + "jpx_listed_202606.xls"
PROCESSED_DIR = ROOT_DIR + "data/processed/"
MERGED_OUTPUT_CSV = PROCESSED_DIR + "tdnet_metadata_all_merged.csv"
PDF_OUTPUT_DIR = RAW_DIR + "tdnet_pdfs/"

OUTPUT_ENCODING = "utf-8-sig"

# ログはプロジェクト直下にまとめる。data/ や models/ と同じ並び。
LOG_DIR = ROOT_DIR + "log/"
# Colabはセッションが切れると出力が消える。LOG_DIR（Drive上）へ標準出力と
# 標準エラーを複製し、切断後も経過を追えるようにする。
LOG_TO_FILE = True
# requests や外部プロセスは fd 2 へ直接書くため、sys.stderr の差し替えでは
# 拾えない。fdごと複製する。
LOG_CAPTURE_NATIVE_STDERR = True
# ログのファイル名に入れる。セルに貼り付けると __file__ が無いので定数で持つ。
SCRIPT_NAME = "fetch_tdnet_metadata"
REQUEST_TIMEOUT = 30
REQUEST_INTERVAL_SEC = 0.2
MAX_RETRIES = 3
MAX_PAGES = 20
MERGE_ALL_EXISTING_DAILIES = True
DOWNLOAD_PDFS = False
PDF_DOWNLOAD_TIMEOUT = 45
PDF_DOWNLOAD_RETRIES = 2
PDF_DOWNLOAD_SLEEP_SEC = 0.15
SKIP_PDF_IF_EXISTS = True

TDNET_BASE = "https://www.release.tdnet.info/inbs/"


# -----------------------------
# 分類の確定（02§3.1）
#   銘柄コード・銘柄名・タイトルだけで決まる分類は、すべてここで付与する。
#   後段で計算し直さない。いずれもLLMを必要としない。
# -----------------------------
# source_type の判定。preprocess_disclosures.py から移設した（02§4.4）。
# 実測98.2%。上から順に評価し、最初に一致したものを採る。
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

# JPXマスタの市場・商品区分から issuer_kind を決める。これが第一の根拠。
MARKET_SEGMENT_TO_ISSUER_KIND: Dict[str, str] = {
    "ETF・ETN": "etf_etn",
    "REIT・ベンチャーファンド・カントリーファンド・インフラファンド": "reit_fund",
}
# JPXマスタ未収載の銘柄（新規上場等・実測69件）を銘柄名の接頭辞で補う。
# 接頭辞のない銘柄にもETF・ETNが345件あるため、接頭辞だけでは取り切れない。
COMPANY_NAME_PREFIX_TO_ISSUER_KIND: Sequence[Tuple[str, str]] = (
    ("Ｅ－", "etf_etn"),
    ("Ｎ－", "etf_etn"),
    ("Ｒ－", "reit_fund"),
    ("Ｉ－", "reit_fund"),
)
DEFAULT_ISSUER_KIND = "operating_company"

# 付与する分類列。preprocess / tag はこれが埋まっている前提で動く。
CLASSIFICATION_FIELDS: Sequence[str] = (
    "jpx_sector_17",
    "jpx_sector_33",
    "jpx_market_segment",
    "issuer_kind",
    "source_type",
)


def classify_source_type(title: str) -> str:
    txt = str(title or "")
    for source_type, pattern in SOURCE_TYPE_RULES:
        if re.search(pattern, txt):
            return source_type
    return "timely_disclosure"


def _jpx_key(code: Any) -> str:
    """TDnetの銘柄コードをJPXマスタのコードに合わせる。

    TDnetは5桁（末尾に1桁付く）、JPXマスタは4桁である。133A0 のような
    英数字コードがあるため、末尾0の除去ではなく先頭4文字を採る。
    """
    return str(code or "").strip()[:4]


def load_jpx_master() -> Dict[str, Dict[str, str]]:
    """コード（4桁）→ 業種・市場区分。"""
    if not os.path.exists(JPX_LISTED_XLS):
        raise FileNotFoundError(
            f"JPX master not found: {JPX_LISTED_XLS}\n"
            "data/master/jpx_listed_202606.xls をDriveへ配置すること。"
        )
    df = pd.read_excel(JPX_LISTED_XLS, dtype=str).fillna("")
    required = ("コード", "銘柄名", "市場・商品区分", "17業種区分", "33業種区分")
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"JPX master is missing columns: {missing} in {JPX_LISTED_XLS}")
    master: Dict[str, Dict[str, str]] = {}
    for _, row in df.iterrows():
        master[str(row["コード"]).strip()] = {
            "jpx_sector_17": str(row["17業種区分"]).strip(),
            "jpx_sector_33": str(row["33業種区分"]).strip(),
            "jpx_market_segment": str(row["市場・商品区分"]).strip(),
        }
    print(f"[info] jpx master: {len(master)} codes from {JPX_LISTED_XLS}")
    return master


def derive_issuer_kind(market_segment: str, company_name: str) -> str:
    """市場・商品区分を第一の根拠とし、未収載は銘柄名の接頭辞で補う。"""
    segment = str(market_segment or "").strip()
    if segment:
        return MARKET_SEGMENT_TO_ISSUER_KIND.get(segment, DEFAULT_ISSUER_KIND)
    name = str(company_name or "")
    for prefix, kind in COMPANY_NAME_PREFIX_TO_ISSUER_KIND:
        if name.startswith(prefix):
            return kind
    return DEFAULT_ISSUER_KIND


def annotate_classification(df: "pd.DataFrame", master: Optional[Dict[str, Dict[str, str]]] = None):
    """メタデータへ分類5項目を付与する。既存の列があっても上書きする。"""
    if df.empty:
        for field in CLASSIFICATION_FIELDS:
            if field not in df.columns:
                df[field] = []
        return df
    if master is None:
        master = load_jpx_master()

    sector_17: List[str] = []
    sector_33: List[str] = []
    segments: List[str] = []
    kinds: List[str] = []
    source_types: List[str] = []
    unlisted = 0
    for _, row in df.iterrows():
        entry = master.get(_jpx_key(row.get("code", "")))
        if entry is None:
            entry = {"jpx_sector_17": "", "jpx_sector_33": "", "jpx_market_segment": ""}
            unlisted += 1
        sector_17.append(entry["jpx_sector_17"])
        sector_33.append(entry["jpx_sector_33"])
        segments.append(entry["jpx_market_segment"])
        kinds.append(derive_issuer_kind(entry["jpx_market_segment"], row.get("company_name", "")))
        source_types.append(classify_source_type(row.get("title", "")))

    df["jpx_sector_17"] = sector_17
    df["jpx_sector_33"] = sector_33
    df["jpx_market_segment"] = segments
    df["issuer_kind"] = kinds
    df["source_type"] = source_types

    kind_counts = Counter(kinds)
    print(
        f"[info] classified {len(df)} rows: "
        + " ".join(f"{k}={v}" for k, v in sorted(kind_counts.items()))
        + f" jpx_unlisted={unlisted}"
    )
    print("[info] source_type: " + " ".join(f"{k}={v}" for k, v in sorted(Counter(source_types).items())))
    return df


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


def _log_path() -> str:
    """<LOG_DIR>/<日時>_<スクリプト名>.txt

    日時を先頭に置き、Driveの名前順が実行順になるようにする。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(LOG_DIR, f"{stamp}_{SCRIPT_NAME}.txt")


def _log_header() -> str:
    """ログ先頭に残す実行条件。あとから同じ実行を再現できる情報を残す。"""
    if FETCH_MODE == "single":
        span = TARGET_DATE
    else:
        span = f"{START_DATE}..{END_DATE}"
    return (
        f"mode={FETCH_MODE} dates={span} download_pdfs={DOWNLOAD_PDFS} "
        f"merge_all={MERGE_ALL_EXISTING_DAILIES} out={ORIGINAL_DIR}"
    )


def _normalize_target_date(value: str) -> Tuple[str, str]:
    dt = datetime.strptime(value, "%Y-%m-%d")
    return dt.strftime("%Y-%m-%d"), dt.strftime("%Y%m%d")


def _date_range_inclusive(start_date: str, end_date: str) -> List[str]:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end < start:
        raise ValueError("END_DATE must be >= START_DATE")
    days: List[str] = []
    cur = start
    while cur <= end:
        days.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return days


def _build_list_url(target_yyyymmdd: str, page_no: int) -> str:
    return f"{TDNET_BASE}I_list_{page_no:03d}_{target_yyyymmdd}.html"


def _safe_filename(value: str, default: str = "document") -> str:
    txt = (value or "").strip()
    txt = re.sub(r"[^0-9A-Za-z._-]+", "_", txt)
    txt = txt.strip("._")
    return txt or default


def _decode_tdnet_html(content: bytes) -> str:
    """
    TDnetはShift_JIS系で配信されることが多いため、cp932を優先して復号する。
    文字化け時の保険として複数エンコーディングを順に試す。
    """
    for enc in ("cp932", "shift_jis", "utf-8", "euc_jp"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _extract_total_count(text: str) -> Optional[int]:
    m = re.search(r"全\s*([0-9,]+)\s*件", text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def _safe_text(tag: Any) -> str:
    if tag is None:
        return ""
    return re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()


def _extract_disclosure_number(doc_href: str) -> str:
    filename = os.path.basename((doc_href or "").strip())
    if not filename:
        return ""
    stem = filename.rsplit(".", 1)[0]
    return stem


def _parse_rows(soup: BeautifulSoup, target_date: str, page_no: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue

        disclosure_time = _safe_text(tds[0])
        if not re.fullmatch(r"\d{2}:\d{2}", disclosure_time):
            continue

        code = _safe_text(tds[1])
        company_name = _safe_text(tds[2])
        title_cell = tds[3]
        market = _safe_text(tds[5]) if len(tds) >= 6 else ""
        update_history = _safe_text(tds[6]) if len(tds) >= 7 else ""

        links = title_cell.find_all("a")
        if not links:
            continue

        doc_href = links[0].get("href", "").strip()
        doc_title = _safe_text(links[0])

        xbrl_href = ""
        for a in links[1:]:
            href = (a.get("href") or "").strip()
            label = _safe_text(a).upper()
            if "XBRL" in label or href.lower().endswith(".zip"):
                xbrl_href = href
                break

        document_url = urljoin(TDNET_BASE, doc_href) if doc_href else ""
        xbrl_url = urljoin(TDNET_BASE, xbrl_href) if xbrl_href else ""
        disclosure_number = _extract_disclosure_number(doc_href)

        rows.append(
            {
                "disclosure_date": target_date,
                "disclosure_time": disclosure_time,
                "disclosure_datetime": f"{target_date} {disclosure_time}:00",
                "disclosure_number": disclosure_number,
                "code": code,
                "company_name": company_name,
                "title": doc_title,
                "document_url": document_url,
                "xbrl_url": xbrl_url,
                "has_xbrl": bool(xbrl_url),
                "market": market,
                "update_history": update_history,
                "list_page": page_no,
                "source_url": _build_list_url(target_date.replace("-", ""), page_no),
            }
        )
    return rows


def _fetch_page(
    session: requests.Session, target_yyyymmdd: str, page_no: int
) -> Optional[BeautifulSoup]:
    url = _build_list_url(target_yyyymmdd, page_no)
    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            html = _decode_tdnet_html(r.content)
            return BeautifulSoup(html, "html.parser")
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(0.8 * attempt)
    raise RuntimeError(f"failed to fetch page={page_no}: {last_error}")


def _build_stable_key(row: pd.Series) -> str:
    document_url = str(row.get("document_url", "") or "").strip()
    disclosure_number = str(row.get("disclosure_number", "") or "").strip()
    if document_url:
        return f"url::{document_url}"
    if disclosure_number:
        return f"disclosure_number::{disclosure_number}"
    disclosure_date = str(row.get("disclosure_date", "") or "").strip()
    disclosure_time = str(row.get("disclosure_time", "") or "").strip()
    code = str(row.get("code", "") or "").strip()
    title = str(row.get("title", "") or "").strip()
    return f"fallback::{disclosure_date}|{disclosure_time}|{code}|{title}"


def _dedupe_tdnet_metadata(df: pd.DataFrame, keep: str = "last") -> pd.DataFrame:
    if df.empty:
        return df.copy()
    work = df.copy()
    if "fetched_at_utc" not in work.columns:
        work["fetched_at_utc"] = ""
    work["_stable_key"] = work.apply(_build_stable_key, axis=1)
    work = work.sort_values(by=["fetched_at_utc"], ascending=True, kind="stable")
    work = work.drop_duplicates(subset=["_stable_key"], keep=keep).reset_index(drop=True)
    work = work.drop(columns=["_stable_key"])
    return work


def _daily_output_csv_path(target_date: str) -> str:
    yyyymmdd = target_date.replace("-", "")
    return ORIGINAL_DIR + f"tdnet_metadata_{yyyymmdd}.csv"


def _daily_pdf_dir_path(target_date: str) -> str:
    yyyymmdd = target_date.replace("-", "")
    return os.path.join(PDF_OUTPUT_DIR, yyyymmdd)


def _save_daily_output(df: pd.DataFrame, target_date: str, encoding: str) -> str:
    output_path = _daily_output_csv_path(target_date)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False, encoding=encoding)
    return output_path


def merge_all_tdnet_daily_csvs(original_dir: str) -> pd.DataFrame:
    pattern = re.compile(r"^tdnet_metadata_\d{8}\.csv$")
    file_names = sorted([name for name in os.listdir(original_dir) if pattern.match(name)])
    if not file_names:
        raise RuntimeError(f"no daily files found under: {original_dir}")

    daily_frames: List[pd.DataFrame] = []
    for file_name in file_names:
        csv_path = os.path.join(original_dir, file_name)
        day_df = pd.read_csv(csv_path, dtype=str).fillna("")
        day_df["source_file"] = file_name
        daily_frames.append(day_df)

    merged = pd.concat(daily_frames, ignore_index=True)
    merged = _dedupe_tdnet_metadata(merged, keep="last")
    merged = merged.sort_values(
        by=["disclosure_date", "disclosure_time", "disclosure_number"],
        ascending=[False, False, False],
        kind="stable",
    ).reset_index(drop=True)
    return merged


def fetch_tdnet_metadata_for_date(target_date: str) -> pd.DataFrame:
    normalized_date, yyyymmdd = _normalize_target_date(target_date)

    session = requests.Session()
    session.headers.update({"User-Agent": "tdnet-metadata-fetcher/1.0"})

    all_rows: List[Dict[str, Any]] = []
    total_count_expected: Optional[int] = None

    for page_no in range(1, MAX_PAGES + 1):
        soup = _fetch_page(session, yyyymmdd, page_no)
        if soup is None:
            print(f"[info] stop: page {page_no:03d} not found (end of pages)")
            break

        page_text = soup.get_text(" ", strip=True)

        if total_count_expected is None:
            total_count_expected = _extract_total_count(page_text)
            if total_count_expected is not None:
                print(f"[info] expected total disclosures: {total_count_expected}")

        page_rows = _parse_rows(soup, normalized_date, page_no)
        if not page_rows:
            print(f"[info] stop: no rows on page {page_no:03d}")
            break

        all_rows.extend(page_rows)
        print(f"[progress] page {page_no:03d}: +{len(page_rows)} rows (total {len(all_rows)})")

        if total_count_expected is not None and len(all_rows) >= total_count_expected:
            print("[info] reached expected total count.")
            break

        if page_no < MAX_PAGES:
            time.sleep(REQUEST_INTERVAL_SEC)
        else:
            print(f"[warn] reached MAX_PAGES={MAX_PAGES}. Increase if needed.")

    if not all_rows:
        raise RuntimeError(
            "No disclosures found. 指定日が休場日か、URL形式変更の可能性があります。"
        )

    df = pd.DataFrame(all_rows)
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    df["fetched_at_utc"] = fetched_at
    df = _dedupe_tdnet_metadata(df, keep="last")
    return df


def _build_pdf_output_path(row: pd.Series, target_date: str) -> str:
    document_url = str(row.get("document_url", "") or "").strip()
    disclosure_number = str(row.get("disclosure_number", "") or "").strip()
    code = str(row.get("code", "") or "").strip()
    date_compact = target_date.replace("-", "")
    parsed = urlparse(document_url)
    base_from_url = os.path.basename(parsed.path) if parsed.path else ""
    suffix = os.path.splitext(base_from_url)[1].lower()
    if suffix != ".pdf":
        suffix = ".pdf"

    if disclosure_number:
        stem = _safe_filename(f"{date_compact}_{code}_{disclosure_number}")
    elif base_from_url:
        stem = _safe_filename(f"{date_compact}_{code}_{os.path.splitext(base_from_url)[0]}")
    else:
        digest = hashlib.sha1(document_url.encode("utf-8")).hexdigest()[:16]
        stem = _safe_filename(f"{date_compact}_{code}_{digest}")

    return os.path.join(_daily_pdf_dir_path(target_date), f"{stem}{suffix}")


def _download_pdf_bytes(session: requests.Session, url: str) -> bytes:
    last_error: Optional[Exception] = None
    for attempt in range(1, PDF_DOWNLOAD_RETRIES + 1):
        try:
            r = session.get(url, timeout=PDF_DOWNLOAD_TIMEOUT)
            r.raise_for_status()
            return r.content
        except Exception as e:
            last_error = e
            if attempt < PDF_DOWNLOAD_RETRIES:
                time.sleep(0.6 * attempt)
    raise RuntimeError(f"download failed after retries: {last_error}")


def download_pdfs_for_date(df: pd.DataFrame, target_date: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    out = df.copy()
    out["pdf_local_path"] = ""
    out["pdf_download_status"] = ""
    out["pdf_file_size_bytes"] = ""
    out["pdf_download_error"] = ""

    os.makedirs(_daily_pdf_dir_path(target_date), exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "tdnet-pdf-downloader/1.0"})

    downloaded = 0
    skipped = 0
    failed = 0

    for idx, row in out.iterrows():
        url = str(row.get("document_url", "") or "").strip()
        if not url:
            out.at[idx, "pdf_download_status"] = "missing_url"
            continue

        save_path = _build_pdf_output_path(row, target_date)
        out.at[idx, "pdf_local_path"] = save_path

        if SKIP_PDF_IF_EXISTS and os.path.exists(save_path):
            out.at[idx, "pdf_download_status"] = "already_exists"
            out.at[idx, "pdf_file_size_bytes"] = str(os.path.getsize(save_path))
            skipped += 1
            continue

        try:
            content = _download_pdf_bytes(session, url)
            with open(save_path, "wb") as f:
                f.write(content)
            out.at[idx, "pdf_download_status"] = "downloaded"
            out.at[idx, "pdf_file_size_bytes"] = str(len(content))
            downloaded += 1
        except Exception as e:
            out.at[idx, "pdf_download_status"] = "failed"
            out.at[idx, "pdf_download_error"] = str(e)
            failed += 1
        time.sleep(PDF_DOWNLOAD_SLEEP_SEC)

    print(
        f"[info] pdf download summary ({target_date}): "
        f"downloaded={downloaded}, skipped={skipped}, failed={failed}"
    )
    return out


def _annotate_existing_dailies(master: Dict[str, Dict[str, str]]) -> List[str]:
    """既存の日次CSVを読み直し、分類5項目を付け直して保存する。

    TDnetへの取得もPDFのダウンロードも行わない。分類ロジックを変えたときに
    メタデータだけを作り直すための経路である（02§3.1）。
    """
    if not os.path.exists(ORIGINAL_DIR):
        raise FileNotFoundError(f"metadata dir not found: {ORIGINAL_DIR}")
    pattern = re.compile(r"^tdnet_metadata_(\d{8})\.csv$")
    days = sorted(m.group(1) for m in (pattern.match(n) for n in os.listdir(ORIGINAL_DIR)) if m)
    if START_DATE and END_DATE:
        allowed = {d.replace("-", "") for d in _date_range_inclusive(START_DATE, END_DATE)}
        days = [d for d in days if d in allowed]
        print(f"[info] annotate range: {START_DATE}..{END_DATE}")
    else:
        print("[info] annotate: all existing dailies (START_DATE/END_DATE 未設定)")
    if not days:
        raise RuntimeError(f"no tdnet_metadata_yyyymmdd.csv to annotate under: {ORIGINAL_DIR}")

    saved: List[str] = []
    for day in days:
        path = os.path.join(ORIGINAL_DIR, f"tdnet_metadata_{day}.csv")
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
        print(f"[info] annotate {day}: {len(df)} rows")
        df = annotate_classification(df, master)
        df.to_csv(path, index=False, encoding=OUTPUT_ENCODING)
        saved.append(path)
        print(f"[done] saved: {path} (encoding={OUTPUT_ENCODING})")
    return saved


@_with_run_log
def main() -> None:
    saved_files: List[str] = []
    failed_dates: List[str] = []
    # 分類はコード突合とタイトル正規表現だけで決まる。LLMは要らない（02§3.1）。
    jpx_master = load_jpx_master()

    if FETCH_MODE == "annotate":
        saved_files = _annotate_existing_dailies(jpx_master)
    elif FETCH_MODE == "single":
        print(f"[info] fetch mode: single ({TARGET_DATE})")
        df = fetch_tdnet_metadata_for_date(TARGET_DATE)
        df = annotate_classification(df, jpx_master)
        if DOWNLOAD_PDFS:
            df = download_pdfs_for_date(df, TARGET_DATE)
        output_csv = _save_daily_output(df, TARGET_DATE, OUTPUT_ENCODING)
        saved_files.append(output_csv)
        print(f"[done] fetched rows: {len(df)}")
        print(f"[done] saved: {output_csv} (encoding={OUTPUT_ENCODING})")
    elif FETCH_MODE == "range":
        target_dates = _date_range_inclusive(START_DATE, END_DATE)
        print(f"[info] fetch mode: range ({START_DATE} ~ {END_DATE}, days={len(target_dates)})")
        for d in target_dates:
            print(f"\n[info] target date: {d}")
            try:
                day_df = fetch_tdnet_metadata_for_date(d)
                day_df = annotate_classification(day_df, jpx_master)
                if DOWNLOAD_PDFS:
                    day_df = download_pdfs_for_date(day_df, d)
                output_csv = _save_daily_output(day_df, d, OUTPUT_ENCODING)
                saved_files.append(output_csv)
                print(f"[done] fetched rows: {len(day_df)}")
                print(f"[done] saved: {output_csv} (encoding={OUTPUT_ENCODING})")
            except Exception as e:
                failed_dates.append(d)
                print(f"[warn] failed date={d}: {e}")
    else:
        raise ValueError("FETCH_MODE must be 'single', 'range' or 'annotate'")

    if MERGE_ALL_EXISTING_DAILIES:
        os.makedirs(PROCESSED_DIR, exist_ok=True)
        merged_df = merge_all_tdnet_daily_csvs(ORIGINAL_DIR)
        merged_df.to_csv(MERGED_OUTPUT_CSV, index=False, encoding=OUTPUT_ENCODING)
        print(f"\n[done] merged all daily files: {len(merged_df)} rows")
        print(f"[done] merged saved: {MERGED_OUTPUT_CSV} (encoding={OUTPUT_ENCODING})")

    if failed_dates:
        print(f"[warn] failed_dates ({len(failed_dates)}): {', '.join(failed_dates)}")

    # Colab上で確認しやすいように先頭を表示
    if saved_files:
        preview_df = pd.read_csv(saved_files[-1], dtype=str).fillna("")
    elif MERGE_ALL_EXISTING_DAILIES:
        preview_df = pd.read_csv(MERGED_OUTPUT_CSV, dtype=str).fillna("")
    else:
        preview_df = pd.DataFrame()
    if not preview_df.empty:
        display_cols = [
            "disclosure_date",
            "code",
            "company_name",
            "issuer_kind",
            "jpx_market_segment",
            "jpx_sector_17",
            "source_type",
            "title",
        ]
        show_cols = [c for c in display_cols if c in preview_df.columns]
        print("\n[preview]")
        print(preview_df[show_cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
