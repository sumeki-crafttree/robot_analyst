# -*- coding: utf-8 -*-

# ==========================================
# マクロテーマ付与（詳細設計 02 §5〜§7・§9）
# Colab 1セル貼り付け実行OK
#
#   前処理JSONL → ゲート → 候補L1絞り込み → スパン抽出 → LLM → 検証
#     → macro_themes_{yyyymmdd}.jsonl（1テーマ言及1行）
#
# 推論は llama.cpp（GGUF）で行い、出力はGBNF文法で拘束する。
# GBNFの l1code / l2code は候補L1に応じてマスタCSVから実行時に生成するため、
# マスタに存在しないコードが返る失敗は構造的に起きない（02§6.4）。
#
# MODE = "tag"    付与を実行する（セッション断からの再開に対応）
# MODE = "report" 出力済みJSONLから受入基準（02§9）の数値を出す。LLMを読み込まない。
# ==========================================

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import shutil
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


# -----------------------------
# 0) 設定（ここだけ編集すればOK）
# -----------------------------
MODE = "tag"  # "tag" | "report"

ROOT_DIR = "/content/drive/MyDrive/git/prop_candidates/"
MASTER_DIR = ROOT_DIR + "data/master/"
PROCESSED_DIR = ROOT_DIR + "data/processed/"
PRODUCT_DIR = ROOT_DIR + "data/product/"
SAMPLE_DIR = ROOT_DIR + "data/samples/"
MODEL_DRIVE_DIR = ROOT_DIR + "models/"
# ログはプロジェクト直下にまとめる。data/ や models/ と同じ並び。
# 他のスクリプトもここへ吐けば、実行履歴を1箇所で追える。
LOG_DIR = ROOT_DIR + "log/"
PROMPT_DIR = ROOT_DIR + "data/prompts/"
MODEL_LOCAL_DIR = "/content/models/"
OUTPUT_ENCODING = "utf-8"

# Colabはセッションが切れると出力が消える。LOG_DIR（Drive上）へ標準出力と
# 標準エラーを複製し、切断後も経過を追えるようにする。
LOG_TO_FILE = True
# ログのファイル名に入れる。どのスクリプトの実行かを区別するため。
# セルに貼り付けると __file__ が無いので定数で持つ。
SCRIPT_NAME = "tag_macro_theme"
# llama.cpp はPythonを介さず fd 2 へ直接書くため、sys.stderr の差し替えでは
# 拾えない。文法エラーやKVキャッシュの警告はそちらに出る。fdごと複製する。
LOG_CAPTURE_NATIVE_STDERR = True

# JSONLに加えてCSVも出す。付与結果をExcelで読めるようにするため。
# runlog の raw_output（違反時の生出力）はCSVには載せない。JSONL側で見る。
WRITE_CSV = True
CSV_ENCODING = "utf-8-sig"  # BOM付き。Excelで開いたときに日本語が化けないようにする。

# L1とL2は1ファイルに統合されている。level列で判別する。
THEME_CSV = MASTER_DIR + "dim_macro_theme_seed.csv"
TAXONOMY_VERSION = "2026-09-07"

PROMPT_VERSION = "v1"
PROMPT_PATH = PROMPT_DIR + f"macro_theme_{PROMPT_VERSION}.txt"

# 入力。前処理JSONLが第一候補。
# 前処理を待たずにプロンプトを試すときは USE_BODIES_SAMPLE=True にする。
# その場合 data/samples/tdnet_bodies_202608.jsonl（本文236件）を直接読む。
USE_BODIES_SAMPLE = False
BODIES_SAMPLE_JSONL = SAMPLE_DIR + "tdnet_bodies_202608.jsonl"

# 処理する日付の範囲。両方空なら全期間。preprocess_disclosures.py と同じ書式。
# tag と report の両方に効く。日単位のファイル名（disclosures_{yyyymmdd}.jsonl /
# macro_themes_{yyyymmdd}.jsonl）で絞るため、範囲外の日は読み込みもしない。
START_DATE = "2026-09-07"  # YYYY-MM-DD または YYYYMMDD
END_DATE = "2026-09-07"

MAX_DOCUMENTS: Optional[int] = None

# --- モデル（02§6）---
# E4B は 12B と同じインターフェースで差し替えられる。速度比較のため。
# GGUFは MODEL_DRIVE_DIR の直下に置く。取得元と手順は下記のとおり。
#
#   !pip install -q huggingface_hub
#   !hf download unsloth/gemma-4-12b-it-GGUF gemma-4-12b-it-UD-Q4_K_XL.gguf \
#       --local-dir /content/drive/MyDrive/git/prop_candidates/models/
#
# 本体の1ファイルだけでよい。mmproj-*.gguf（画像・音声用プロジェクタ）と
# mtp-*.gguf（Multi-Token Prediction）は本用途では使わない。
#
# 既定は UD-Q4_K_XL とする。02§6.2 が「Q4_K_M を基本とし、Unsloth の
# UD-Q4_K_XL のような改良版があればそちらを優先する」としており、実在するため。
MODEL_KEY = "12b_ud"
MODEL_PRESETS: Dict[str, Dict[str, Any]] = {
    # 本命。unsloth/gemma-4-12b-it-GGUF
    "12b_ud": {
        "gguf_file": "gemma-4-12b-it-UD-Q4_K_XL.gguf",  # 7.37GB
        "model_name": "gemma-4-12b-it-ud-q4_k_xl",
        "n_ctx": 8192,
    },
    "12b": {
        "gguf_file": "gemma-4-12b-it-Q4_K_M.gguf",  # 7.12GB
        "model_name": "gemma-4-12b-it-q4_k_m",
        "n_ctx": 8192,
    },
    # 量子化水準の比較用（02§9）。12.7GBでT4 16GBにぎりぎり載る。
    "12b_q8": {
        "gguf_file": "gemma-4-12b-it-Q8_0.gguf",  # 12.7GB
        "model_name": "gemma-4-12b-it-q8_0",
        "n_ctx": 8192,
    },
    # 速度側の比較対象。unsloth/gemma-4-E4B-it-GGUF
    # ファイル名の E4B は大文字。小文字にするとDrive上で見つからない。
    "e4b_ud": {
        "gguf_file": "gemma-4-E4B-it-UD-Q4_K_XL.gguf",
        "model_name": "gemma-4-e4b-it-ud-q4_k_xl",
        "n_ctx": 8192,
    },
    "e4b": {
        "gguf_file": "gemma-4-E4B-it-Q4_K_M.gguf",
        "model_name": "gemma-4-e4b-it-q4_k_m",
        "n_ctx": 8192,
    },
}

# T4はbfloat16にもFlash Attention 2にも非対応。llama.cppのGGUFはfp16/量子化で
# 動くためこの制約に抵触しないが、n_gpu_layers=-1 で全層GPUに載せる前提である。
N_GPU_LAYERS = -1
# 実行の冒頭でGPUの有無を確かめる。CPUランタイムのままだと llama_cpp の import が
# 「libcudart.so.12 が無い」という分かりにくい形で落ちるため、
# モデルを7GB落とす前にここで止める。
REQUIRE_GPU = True
N_BATCH = 512
MAX_OUTPUT_TOKENS = 512
TEMPERATURE = 0.0  # 再現性のため（01§6.1）

# Colab向け。CUDA版のprebuilt wheelを先に試し、失敗したら通常のpipへ落とす。
LLAMA_CPP_WHEEL_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/cu124"

# --- ゲートとスパン（02§5.2 / §5.3）---
EVIDENCE_CONTEXT_WINDOW = 1  # ヒットブロックの前後何ブロックを連結するか
MAX_SPAN_CHAR_COUNT = 1200  # 1スパンの上限
MAX_TOTAL_SPAN_CHAR_COUNT = 4000  # 1文書のスパン合計の上限
SKIP_BLOCK_TYPES: Sequence[str] = ("header", "footer")
SPAN_JOINER = "\n\n"  # スパン連結の区切り。合計字数の計算にも使う。

# `other` は typical_expressions が空でゲートに絶対ヒットしないため、
# 常に候補へ含める。そうしないと「マクロ要因はあるが15テーマのどれでもない」
# をLLMが表明できず、02§9 の other 率が構造的に0になって指標として死ぬ。
ALWAYS_INCLUDE_OTHER = True
OTHER_THEME_CODE = "other"

MAX_THEMES_PER_DOCUMENT = 3  # 01§6.3
MAX_EVIDENCE_CHARS_IN_GRAMMAR = 200

# 01§6.5 の較正。True にするとゲートで落ちた文書にもLLMを呼び、
# ゲートの取りこぼし（false negative）を測れる。候補L1は全16テーマになる。
# 既定は False。02§8.2 のスループット見積り（ゲート通過分のみ）に合わせる。
CALIBRATION_MODE = False


def _run_tag() -> str:
    return f"{MODEL_PRESETS[MODEL_KEY]['model_name']}__{PROMPT_VERSION}"


def _run_dir() -> str:
    return os.path.join(PRODUCT_DIR, _run_tag())


def _log_path() -> str:
    """<LOG_DIR>/<日時>_<スクリプト名>__<run_tag>.txt

    日時を先頭に置き、Driveの名前順が実行順になるようにする。
    run_tag（モデル名とプロンプト版）まで入れて、開かずに区別できるようにする。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(LOG_DIR, f"{stamp}_{SCRIPT_NAME}__{_run_tag()}.txt")


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
            f"model={MODEL_KEY} prompt={PROMPT_VERSION} taxonomy={TAXONOMY_VERSION} =====\n"
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


# -----------------------------
# 1) 文字列正規化
#    ゲート照合は前処理と同じ正規化のうえで素朴な部分一致を取る。
#    この方式で 2026-09-01 の実測（timely 34.5% / forecast 50.0% /
#    earnings 95.9% / presentation 92.6%）を再現できることを確認済み。
# -----------------------------
def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    txt = unicodedata.normalize("NFKC", str(value))
    txt = txt.replace("　", " ")
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def allowed_days() -> Optional[Set[str]]:
    """START_DATE / END_DATE から対象日の集合を作る。両方空なら None（全期間）。"""
    if not START_DATE and not END_DATE:
        return None
    if not (START_DATE and END_DATE):
        raise ValueError("If using date range, set both START_DATE and END_DATE")
    return set(_date_range_inclusive(START_DATE, END_DATE))


def _date_to_compact(value: str) -> str:
    txt = str(value or "").strip().replace("/", "-")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", txt)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    if re.match(r"^\d{8}$", txt):
        return txt
    return re.sub(r"\D+", "", txt)[:8] or "unknown_date"


# -----------------------------
# 2) マスタ（UTF-8 with BOM。encoding='utf-8-sig' 必須。01§5.1）
# -----------------------------
class Taxonomy:
    def __init__(self, themes: List[Dict[str, str]], subthemes: List[Dict[str, str]]) -> None:
        self.themes = themes
        self.subthemes = subthemes
        self.theme_by_code = {t["theme_code"]: t for t in themes}
        self.subtheme_by_code = {s["subtheme_code"]: s for s in subthemes}
        self.subthemes_by_theme: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        for s in subthemes:
            self.subthemes_by_theme[s["theme_code"]].append(s)

        # ゲート語彙: 正規化語 → 属するL1コードの集合
        self.gate_terms: Dict[str, Set[str]] = defaultdict(set)
        self.term_display: Dict[str, str] = {}
        for t in themes:
            for term in str(t.get("typical_expressions", "")).split("|"):
                term = term.strip()
                if not term:
                    continue
                key = _normalize_text(term)
                self.gate_terms[key].add(t["theme_code"])
                self.term_display[key] = term
        for s in subthemes:
            for term in str(s.get("typical_expressions", "")).split("|"):
                term = term.strip()
                if not term:
                    continue
                key = _normalize_text(term)
                self.gate_terms[key].add(s["theme_code"])
                self.term_display[key] = term

    @property
    def all_theme_codes(self) -> List[str]:
        return [t["theme_code"] for t in self.themes]


def _repo_dir() -> str:
    """このスクリプトが置かれているリポジトリのルート。

    Colabでは「Driveに置く」「/content にcloneする」「セルに貼り付ける」の
    どれもあり得る。セルに貼った場合は __file__ が無いのでカレントで代用する。
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        here = os.getcwd()
    return os.path.dirname(here) if os.path.basename(here) == "notebook" else here


def resolve_input_path(drive_path: str, repo_relative: str, what: str) -> str:
    """入力ファイルを Drive → リポジトリ → カレント の順に探す。

    マスタCSVとプロンプトはリポジトリの管理物であり、Driveにコピーしていなくても
    cloneしてあれば見つかるようにする。
    """
    repo = _repo_dir()
    candidates = [
        drive_path,
        os.path.join(repo, repo_relative),
        os.path.join(os.getcwd(), repo_relative),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    raise FileNotFoundError(f"{what} not found. searched: {candidates}")


def _read_csv_utf8_sig(path: str) -> List[Dict[str, str]]:
    import csv

    # BOMを除去しないと1列目のカラム名が壊れ、突合が全件失敗する（01§5.1）
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(f)]


def load_taxonomy() -> Taxonomy:
    """マスタは1ファイル。level列でL1/L2に分ける。

    L1は definition / includes / excludes を持ち、L2は空。name列は
    L1では theme_name、L2では subtheme_name として下流へ渡す。
    """
    theme_path = resolve_input_path(
        THEME_CSV, "data/master/dim_macro_theme_seed.csv", "dim_macro_theme_seed.csv"
    )
    print(f"[info] master: {theme_path}")
    rows = _read_csv_utf8_sig(theme_path)

    themes: List[Dict[str, str]] = []
    subthemes: List[Dict[str, str]] = []
    for r in rows:
        level = (r.get("level") or "").strip().upper()
        if level == "L1":
            themes.append({**r, "theme_name": r.get("name", "")})
        elif level == "L2":
            subthemes.append({**r, "subtheme_name": r.get("name", "")})
        else:
            raise ValueError(f"level列がL1/L2以外です: {r!r}")
    if not themes or not subthemes:
        raise ValueError(f"L1={len(themes)} L2={len(subthemes)}。マスタのlevel列を確認すること。")
    tx = Taxonomy(themes, subthemes)
    print(f"[info] taxonomy L1={len(themes)} L2={len(subthemes)} gate_terms={len(tx.gate_terms)}")
    if len(tx.gate_terms) != 239:
        print(f"[warn] gate term count is {len(tx.gate_terms)}, expected 239. マスタを確認すること。")
    return tx


# -----------------------------
# 3) 入力
# -----------------------------
def _pseudo_blocks_from_text(text: str) -> List[Dict[str, Any]]:
    """blocks を持たない入力（tdnet_bodies_202608.jsonl）向けの退避処理。

    PyMuPDFのブロックに相当する単位が無いため、改行で切ったうえで
    短い行を連結し、200字程度のまとまりに均す。プロンプト試行用であり、
    層化サンプルの本番経路は前処理JSONLの実ブロックを使う。
    """
    blocks: List[Dict[str, Any]] = []
    buf: List[str] = []
    buf_len = 0
    for raw_line in str(text or "").split("\n"):
        line = _normalize_text(raw_line)
        if not line:
            continue
        buf.append(line)
        buf_len += len(line)
        if buf_len >= 200:
            blocks.append({"i": len(blocks), "page": 1, "text": " ".join(buf), "type": "paragraph"})
            buf, buf_len = [], 0
    if buf:
        blocks.append({"i": len(blocks), "page": 1, "text": " ".join(buf), "type": "paragraph"})
    return blocks


def load_documents() -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    days = allowed_days()

    if USE_BODIES_SAMPLE:
        bodies_path = resolve_input_path(
            BODIES_SAMPLE_JSONL, "data/samples/tdnet_bodies_202608.jsonl", "bodies sample"
        )
        for line in open(bodies_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            day = _date_to_compact(r.get("disclosure_date", ""))
            if days is not None and day not in days:
                continue
            text = _normalize_text(r.get("body_text", ""))
            seed = str(r.get("document_url", "")) or f"{day}{r.get('title', '')}"
            docs.append(
                {
                    "document_id": f"{day}_{r.get('code', '')}_{_sha256_hex(seed)[:8]}",
                    "disclosure_date": r.get("disclosure_date", ""),
                    "code": r.get("code", ""),
                    "company_name": r.get("company_name", ""),
                    "title": r.get("title", ""),
                    "source_type": r.get("source_type", ""),
                    "jpx_sector_17": r.get("jpx_sector_17", ""),
                    "text": text,
                    "blocks": _pseudo_blocks_from_text(r.get("body_text", "")),
                    "status": "ok",
                }
            )
        print(f"[info] documents from bodies sample: {len(docs)}"
              + (f" days={START_DATE}..{END_DATE}" if days is not None else ""))
        return docs

    if not os.path.exists(PROCESSED_DIR):
        raise FileNotFoundError(f"processed dir not found: {PROCESSED_DIR}")
    pattern = re.compile(r"^disclosures_(\d{8})\.jsonl$")
    matched = [(m.group(1), m.group(0)) for m in (pattern.match(n) for n in os.listdir(PROCESSED_DIR)) if m]
    if not matched:
        raise RuntimeError(
            f"no disclosures_yyyymmdd.jsonl under: {PROCESSED_DIR}\n"
            "preprocess_disclosures.py を先に実行してください。"
        )
    names = sorted(name for day, name in matched if days is None or day in days)
    if not names:
        raise RuntimeError(
            f"no disclosures file in range {START_DATE}..{END_DATE} under: {PROCESSED_DIR}\n"
            f"存在するのは {sorted(d for d, _ in matched)} です。"
        )
    for name in names:
        for line in open(os.path.join(PROCESSED_DIR, name), encoding="utf-8"):
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    print(f"[info] documents from processed: {len(docs)} files={len(names)}"
          + (f" days={START_DATE}..{END_DATE}" if days is not None else ""))
    return docs


# -----------------------------
# 4) ゲート（02§5.1 / 01§6.5）
# -----------------------------
def run_gate(text: str, tx: Taxonomy) -> Tuple[List[str], List[str]]:
    """本文にマクロ語彙が出現するか。戻り値は (ヒット語, 候補L1)。

    ゲートは「除外」にのみ用いる。語の出現はテーマの存在を意味しない（01§6.5）。
    """
    haystack = _normalize_text(text)
    if not haystack:
        return [], []
    hit_terms: List[str] = []
    hit_themes: Counter = Counter()
    for key, theme_codes in tx.gate_terms.items():
        if key and key in haystack:
            hit_terms.append(tx.term_display.get(key, key))
            for code in theme_codes:
                hit_themes[code] += 1
    candidates = [code for code, _ in hit_themes.most_common()]
    return sorted(set(hit_terms)), candidates


# -----------------------------
# 5) スパン抽出（02§5.2）
# -----------------------------
def build_spans(
    blocks: Sequence[Dict[str, Any]], tx: Taxonomy
) -> Tuple[List[str], Dict[str, int]]:
    """ヒット語を含むブロック±1を連結してスパンにする。

    既存 tdnet_pdf_preprocessing.py の EVIDENCE_CONTEXT_WINDOW と同じ考え方で、
    キーワード配列をマスタ語彙に差し替えたもの。
    """
    usable = [b for b in blocks if str(b.get("type", "")) not in SKIP_BLOCK_TYPES]
    if not usable:
        return [], {}

    norm_texts = [_normalize_text(b.get("text", "")) for b in usable]
    theme_freq: Counter = Counter()

    hits: List[Tuple[int, Set[str]]] = []
    for idx, ntext in enumerate(norm_texts):
        if not ntext:
            continue
        themes_here: Set[str] = set()
        for key, theme_codes in tx.gate_terms.items():
            if key and key in ntext:
                themes_here |= theme_codes
        if themes_here:
            hits.append((idx, themes_here))
            for code in themes_here:
                theme_freq[code] += 1

    # ヒットが隣接すると ±1 のウィンドウ同士が重なる。重なり・連続する範囲は
    # 併合してから切り出す（02§5.2「スパンは重複排除する」）。
    # 併合しないと同じ本文が繰り返し載り、実測でスパン全体の23.5%が重複した。
    # 4,000字の上限に達する文書が62%あるため、重複はそのまま実証拠を押し出す。
    windows: List[Tuple[Any, int, int, Set[str], int]] = []
    for order, (idx, themes_here) in enumerate(hits):
        page = usable[idx].get("page")
        lo, hi = idx, idx
        for j in range(idx - EVIDENCE_CONTEXT_WINDOW, idx + EVIDENCE_CONTEXT_WINDOW + 1):
            if 0 <= j < len(usable) and usable[j].get("page") == page:
                lo, hi = min(lo, j), max(hi, j)
        windows.append((page, lo, hi, set(themes_here), order))

    windows.sort(key=lambda w: (str(w[0]), w[1]))
    merged: List[Tuple[Any, int, int, Set[str], int]] = []
    for page, lo, hi, themes_here, order in windows:
        if merged and merged[-1][0] == page and lo <= merged[-1][2] + 1:
            p_page, p_lo, p_hi, p_themes, p_order = merged[-1]
            merged[-1] = (p_page, p_lo, max(p_hi, hi), p_themes | themes_here, min(p_order, order))
        else:
            merged.append((page, lo, hi, themes_here, order))

    candidates: List[Tuple[int, int, str]] = []  # (priority, order, span_text)
    for _, lo, hi, themes_here, order in merged:
        span_text = "\n".join(norm_texts[j] for j in range(lo, hi + 1) if norm_texts[j]).strip()
        if not span_text:
            continue
        if len(span_text) > MAX_SPAN_CHAR_COUNT:
            span_text = span_text[:MAX_SPAN_CHAR_COUNT]
        # 出現頻度の高いL1のスパンを優先する（02§5.2）
        priority = max((theme_freq[c] for c in themes_here), default=0)
        candidates.append((priority, order, span_text))

    candidates.sort(key=lambda x: (-x[0], x[1]))

    spans: List[str] = []
    total = 0
    for _, _, span_text in candidates:
        # 連結時の区切り（"\n\n"）も合計に数える。プロンプトに載る実長で打ち切る。
        joiner = 0 if not spans else len(SPAN_JOINER)
        if total + joiner + len(span_text) > MAX_TOTAL_SPAN_CHAR_COUNT:
            remaining = MAX_TOTAL_SPAN_CHAR_COUNT - total - joiner
            if remaining >= 200:
                spans.append(span_text[:remaining])
                total += joiner + remaining
            break
        spans.append(span_text)
        total += joiner + len(span_text)
    return spans, dict(theme_freq)


# -----------------------------
# 6) GBNF文法（02§6.4）
#    候補L1ごとに専用のオブジェクト規則を作る。L2の選択肢もL1配下に閉じるため、
#    「別L1のL2を返す」誤りも文法段階で起きない。
# -----------------------------
# GBNFの規則名に使えるのは英数字とハイフンだけである（llama.cpp の is_word_char）。
# アンダースコアを残すと theme-commodity_price が theme-commodity までしか
# 名前として読まれず、"error parsing grammar: expecting newline or end at _price"
# となる。llama.cpp は不正な文法ポインタを返し、推論時にカーネルごと落ちる。
_GBNF_NAME_RE = re.compile(r"^[A-Za-z0-9-]+$")


def _gbnf_rule_name(prefix: str, code: str) -> str:
    return f"{prefix}-{re.sub(r'[^0-9a-zA-Z]', '-', code)}"


def _validate_gbnf(text: str) -> None:
    """規則名の文字種を検証する。文法エラーはPython側で落とす。

    llama.cpp に不正な文法を渡すとカーネルごと落ちるため、
    原因の分からないクラッシュにせず、ここで止める。
    """
    seen: Dict[str, str] = {}
    for line in text.splitlines():
        if "::=" not in line:
            continue
        name = line.split("::=", 1)[0].strip()
        if not _GBNF_NAME_RE.match(name):
            raise ValueError(
                f"GBNFの規則名に使えない文字がある: {name!r}。"
                "使えるのは英数字とハイフンのみ。"
            )
        if name in seen:
            raise ValueError(f"GBNFの規則名が重複している: {name!r}")
        seen[name] = line


def build_grammar(candidate_theme_codes: Sequence[str], tx: Taxonomy) -> str:
    codes = [c for c in candidate_theme_codes if c in tx.theme_by_code]
    if not codes:
        codes = [OTHER_THEME_CODE] if OTHER_THEME_CODE in tx.theme_by_code else tx.all_theme_codes

    lines: List[str] = []
    lines.append('root ::= "{" ws "\\"themes\\"" ws ":" ws themes ws "}"')
    max_extra = max(0, MAX_THEMES_PER_DOCUMENT - 1)
    lines.append(
        'themes ::= "[" ws "]" | "[" ws theme (ws "," ws theme){0,%d} ws "]"' % max_extra
    )
    lines.append("theme ::= " + " | ".join(_gbnf_rule_name("theme", c) for c in codes))

    for code in codes:
        l2_rule = _gbnf_rule_name("l2", code)
        lines.append(
            '{name} ::= "{{" ws "\\"theme_code\\"" ws ":" ws "\\"{code}\\"" ws ","'
            ' ws "\\"subtheme_code\\"" ws ":" ws {l2} ws ","'
            ' ws "\\"direction\\"" ws ":" ws direction ws ","'
            ' ws "\\"evidence_text\\"" ws ":" ws string ws ","'
            ' ws "\\"extraction_confidence\\"" ws ":" ws confidence ws "}}"'.format(
                name=_gbnf_rule_name("theme", code), code=code, l2=l2_rule
            )
        )
        subcodes = [s["subtheme_code"] for s in tx.subthemes_by_theme.get(code, [])]
        alts = ['"null"'] + ['"\\"%s\\""' % sc for sc in subcodes]
        lines.append(f"{l2_rule} ::= " + " | ".join(alts))

    lines.append('direction ::= "\\"up\\"" | "\\"down\\"" | "\\"neutral\\"" | "\\"unknown\\""')
    lines.append('confidence ::= ("0." [0-9]) | "1.0"')
    lines.append('string ::= "\\"" char{0,%d} "\\""' % MAX_EVIDENCE_CHARS_IN_GRAMMAR)
    lines.append(r'char ::= [^"\\\n\r\t] | "\\" ["\\/bfnrt]')
    lines.append("ws ::= [ \\t\\n]*")
    text = "\n".join(lines) + "\n"
    _validate_gbnf(text)
    return text


# -----------------------------
# 7) プロンプト（02§7.2 コード内の文字列リテラルにしない）
# -----------------------------
def resolve_prompt_path() -> str:
    """プロンプトはコード内の文字列リテラルにしない（02§7.2）。

    Drive上・リポジトリを /content にcloneした場合・カレント直下の順に探す。
    """
    name = f"macro_theme_{PROMPT_VERSION}.txt"
    return resolve_input_path(PROMPT_PATH, f"notebook/prompts/{name}", name)


def load_prompt_template() -> str:
    path = resolve_prompt_path()
    print(f"[info] prompt: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def render_prompt(
    template: str,
    candidate_theme_codes: Sequence[str],
    tx: Taxonomy,
    title: str,
    source_type: str,
    spans: Sequence[str],
) -> str:
    theme_lines: List[str] = []
    subtheme_lines: List[str] = []
    for code in candidate_theme_codes:
        t = tx.theme_by_code.get(code)
        if not t:
            continue
        theme_lines.append(
            f"- `{code}`（{t.get('theme_name', '')}）\n"
            f"  定義: {t.get('definition', '')}\n"
            f"  含む: {t.get('includes', '') or '—'}\n"
            f"  含まない: {t.get('excludes', '') or '—'}"
        )
        subs = tx.subthemes_by_theme.get(code, [])
        if subs:
            subtheme_lines.append(f"- `{code}` 配下:")
            for sub in subs:
                examples = str(sub.get("typical_expressions", "")).strip()
                suffix = f" 例: {examples}" if examples else ""
                subtheme_lines.append(
                    f"    - `{sub['subtheme_code']}`（{sub.get('subtheme_name', '')}）{suffix}"
                )
        else:
            subtheme_lines.append(f"- `{code}` 配下: サブテーマなし。必ず null を返す。")

    body = SPAN_JOINER.join(f"[抜粋 {i + 1}]\n{s}" for i, s in enumerate(spans))
    out = template
    out = out.replace("{{THEME_DEFINITIONS}}", "\n".join(theme_lines))
    out = out.replace("{{SUBTHEME_DEFINITIONS}}", "\n".join(subtheme_lines))
    out = out.replace("{{DOCUMENT_TITLE}}", str(title or ""))
    out = out.replace("{{SOURCE_TYPE}}", str(source_type or ""))
    out = out.replace("{{SPANS}}", body)
    return out


GEMMA_TURN_TEMPLATE = "<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"


# -----------------------------
# 8) モデル（02§6.3）
# -----------------------------
def assert_gpu_available() -> None:
    """GPUランタイムであることを確かめる。無ければ理由を示して止める。

    02§3 はColab無料枠のT4（VRAM 16GB）を前提とし、N_GPU_LAYERS=-1 で
    全層をGPUへ載せる。CPUランタイムでは12Bは現実的な時間で終わらない。
    """
    if not REQUIRE_GPU or N_GPU_LAYERS == 0:
        return

    hint = (
        "\n  Colab: ランタイム → ランタイムのタイプを変更 → T4 GPU → 保存"
        "\n  CPUで動かすなら REQUIRE_GPU=False と N_GPU_LAYERS=0 にすること"
        "（12Bでは1件あたり分単位になり非現実的）。"
    )
    if shutil.which("nvidia-smi") is None:
        raise RuntimeError("GPUランタイムではない（nvidia-smi が無い）。" + hint)
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            text=True,
            timeout=60,
        ).strip()
    except Exception as e:
        raise RuntimeError(
            f"nvidia-smi の実行に失敗した（{type(e).__name__}: {e}）。" + hint
        ) from e
    if not out:
        raise RuntimeError("GPUが検出できない（nvidia-smi の出力が空）。" + hint)

    print(f"[info] gpu: {' / '.join(out.splitlines())}")
    for line in out.splitlines():
        m = re.search(r"(\d+)\s*MiB", line)
        if m and int(m.group(1)) < 15000:
            print(
                f"[warn] VRAM {m.group(1)}MiB。02§3 はT4の16GBを前提としている。"
                f" MODEL_KEY={MODEL_KEY} が載らない可能性がある。"
            )


def _install_llama_cpp() -> None:
    try:
        __import__("llama_cpp")
        return
    except Exception:
        pass
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "llama-cpp-python",
             "--extra-index-url", LLAMA_CPP_WHEEL_INDEX]
        )
    except Exception as e:
        print(f"[warn] CUDA wheel install failed ({e}). falling back to plain pip (CPU build).")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "llama-cpp-python"])


def stage_model() -> str:
    """Driveから /content へコピーしてから読む。DriveのI/Oは推論の律速になる。"""
    preset = MODEL_PRESETS[MODEL_KEY]
    src = os.path.join(MODEL_DRIVE_DIR, preset["gguf_file"])
    if not os.path.exists(src):
        raise FileNotFoundError(f"gguf not found on Drive: {src}")
    os.makedirs(MODEL_LOCAL_DIR, exist_ok=True)
    dst = os.path.join(MODEL_LOCAL_DIR, preset["gguf_file"])
    if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
        print(f"[info] model already staged: {dst}")
        return dst
    size_gb = os.path.getsize(src) / (1024 ** 3)
    print(f"[info] copying model to /content ({size_gb:.1f}GB). 3〜7分かかる。")
    started = time.time()
    shutil.copyfile(src, dst)
    print(f"[info] copied in {(time.time() - started) / 60:.1f} min: {dst}")
    return dst


def load_llm(model_path: str):
    _install_llama_cpp()
    from llama_cpp import Llama  # type: ignore

    preset = MODEL_PRESETS[MODEL_KEY]
    print(f"[info] loading {preset['model_name']} n_gpu_layers={N_GPU_LAYERS}")
    return Llama(
        model_path=model_path,
        n_ctx=int(preset["n_ctx"]),
        n_gpu_layers=N_GPU_LAYERS,
        n_batch=N_BATCH,
        logits_all=False,
        verbose=False,
    )


def generate_json(llm, prompt: str, grammar_text: str) -> str:
    from llama_cpp import LlamaGrammar  # type: ignore

    grammar = LlamaGrammar.from_string(grammar_text, verbose=False)
    out = llm.create_completion(
        prompt=GEMMA_TURN_TEMPLATE.format(prompt=prompt),
        grammar=grammar,
        temperature=TEMPERATURE,
        max_tokens=MAX_OUTPUT_TOKENS,
        stop=["<end_of_turn>"],
    )
    return out["choices"][0]["text"]


# -----------------------------
# 9) 検証（02§5.1 [5]）
# -----------------------------
def validate_themes(
    parsed: Any, candidate_theme_codes: Sequence[str], tx: Taxonomy, span_text: str
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """GBNF下では原則ここで弾かれない。弾かれたら文法定義の誤りである。"""
    violations: List[str] = []
    if not isinstance(parsed, dict) or not isinstance(parsed.get("themes"), list):
        return [], ["root_schema"]

    allowed = set(candidate_theme_codes)
    haystack = _normalize_text(span_text)
    out: List[Dict[str, Any]] = []
    seen_codes: Set[str] = set()

    for item in parsed["themes"][:MAX_THEMES_PER_DOCUMENT]:
        if not isinstance(item, dict):
            violations.append("theme_not_object")
            continue
        code = item.get("theme_code")
        if code not in tx.theme_by_code:
            violations.append(f"unknown_theme_code:{code}")
            continue
        if code not in allowed:
            violations.append(f"theme_code_out_of_candidates:{code}")
            continue
        sub = item.get("subtheme_code")
        if sub is not None:
            if sub not in tx.subtheme_by_code:
                violations.append(f"unknown_subtheme_code:{sub}")
                sub = None
            elif tx.subtheme_by_code[sub]["theme_code"] != code:
                violations.append(f"subtheme_theme_mismatch:{sub}")
                sub = None
        direction = item.get("direction")
        if direction not in ("up", "down", "neutral", "unknown"):
            violations.append(f"bad_direction:{direction}")
            direction = "unknown"
        evidence = _normalize_text(item.get("evidence_text", ""))
        if not evidence:
            violations.append("empty_evidence")
            continue
        # 文法で防げるのは構文だけである。evidenceが原文に含まれるかはここで見る。
        evidence_in_source = evidence in haystack
        try:
            confidence = float(item.get("extraction_confidence", 0.0))
        except Exception:
            violations.append("bad_confidence")
            confidence = 0.0
        if code in seen_codes:
            violations.append(f"duplicate_theme_code:{code}")
            continue
        seen_codes.add(code)
        out.append(
            {
                "theme_code": code,
                "subtheme_code": sub,
                "direction": direction,
                "evidence_text": evidence,
                "extraction_confidence": round(max(0.0, min(1.0, confidence)), 2),
                "evidence_in_source": evidence_in_source,
            }
        )
    return out, violations


# -----------------------------
# 10) 出力（02§5.4）
# -----------------------------
def _theme_mention_id(document_id: str, theme_code: Any, subtheme_code: Any, evidence: str) -> str:
    seed = f"{document_id}{theme_code}{subtheme_code}{evidence}"
    return _sha256_hex(seed)[:16]


def _themes_path(day: str) -> str:
    return os.path.join(_run_dir(), f"macro_themes_{day}.jsonl")


def _runlog_path(day: str) -> str:
    return os.path.join(_run_dir(), f"runlog_{day}.jsonl")


def _themes_csv_path(day: str) -> str:
    return os.path.join(_run_dir(), f"macro_themes_{day}.csv")


def _runlog_csv_path(day: str) -> str:
    return os.path.join(_run_dir(), f"runlog_{day}.csv")


THEME_CSV_FIELDS: Sequence[str] = (
    "theme_mention_id",
    "document_id",
    "disclosure_date",
    "code",
    "company_name",
    "title",
    "source_type",
    "jpx_sector_17",
    "theme_code",
    "subtheme_code",
    "direction",
    "evidence_text",
    "extraction_confidence",
    "evidence_in_source",
    "gate_hit_terms",
    "model",
    "prompt_version",
    "taxonomy_version",
)

RUNLOG_CSV_FIELDS: Sequence[str] = (
    "document_id",
    "disclosure_date",
    "source_type",
    "jpx_sector_17",
    "preprocess_status",
    "gate_passed",
    "gate_hit_term_count",
    "candidate_theme_codes",
    "candidate_theme_count",
    "llm_called",
    "span_chars",
    "theme_count",
    "schema_violations",
    "elapsed_sec",
    "model",
    "prompt_version",
    "calibration_mode",
    "processed_at_utc",
)


def _flatten_for_csv(row: Dict[str, Any], fields: Sequence[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in fields:
        value = row.get(key)
        if isinstance(value, (list, tuple)):
            value = "|".join(str(v) for v in value)
        out[key] = "" if value is None else value
    return out


def open_csv_appender(path: str, fields: Sequence[str]):
    """追記用のCSVを開く。新規または空のときだけヘッダを書く。"""
    import csv

    is_new = (not os.path.exists(path)) or os.path.getsize(path) == 0
    handle = open(path, "a", encoding=CSV_ENCODING, newline="")
    writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
    if is_new:
        writer.writeheader()
        handle.flush()
    return handle, writer


def load_processed_ids() -> Set[str]:
    """起動時に出力JSONLを読み、処理済み document_id を集める（02§8.3・必須要件）。"""
    done: Set[str] = set()
    run_dir = _run_dir()
    if not os.path.exists(run_dir):
        return done
    for name in sorted(os.listdir(run_dir)):
        if not re.match(r"^macro_themes_\d{8}\.jsonl$", name):
            continue
        for line in open(os.path.join(run_dir, name), encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["document_id"])
            except Exception:
                continue
    return done


# -----------------------------
# 11) 付与本体
# -----------------------------
@_with_run_log
def tag_all() -> None:
    assert_gpu_available()
    tx = load_taxonomy()
    template = load_prompt_template()
    os.makedirs(_run_dir(), exist_ok=True)

    docs = load_documents()
    docs.sort(key=lambda d: (_date_to_compact(d.get("disclosure_date", "")), str(d.get("code", ""))))
    if MAX_DOCUMENTS is not None and MAX_DOCUMENTS > 0:
        docs = docs[:MAX_DOCUMENTS]

    processed = load_processed_ids()
    print(f"[info] already processed: {len(processed)} / {len(docs)}")

    llm = None
    model_name = MODEL_PRESETS[MODEL_KEY]["model_name"]
    theme_handles: Dict[str, Any] = {}
    runlog_handles: Dict[str, Any] = {}
    theme_csv: Dict[str, Any] = {}
    theme_csv_w: Dict[str, Any] = {}
    runlog_csv: Dict[str, Any] = {}
    runlog_csv_w: Dict[str, Any] = {}
    started = time.time()
    counters: Counter = Counter()

    try:
        for n, doc in enumerate(docs, 1):
            document_id = str(doc.get("document_id", ""))
            if document_id in processed:
                counters["skipped_done"] += 1
                continue

            day = _date_to_compact(doc.get("disclosure_date", ""))
            if day not in theme_handles:
                theme_handles[day] = open(_themes_path(day), "a", encoding=OUTPUT_ENCODING)
                runlog_handles[day] = open(_runlog_path(day), "a", encoding=OUTPUT_ENCODING)
                if WRITE_CSV:
                    theme_csv[day], theme_csv_w[day] = open_csv_appender(
                        _themes_csv_path(day), THEME_CSV_FIELDS
                    )
                    runlog_csv[day], runlog_csv_w[day] = open_csv_appender(
                        _runlog_csv_path(day), RUNLOG_CSV_FIELDS
                    )

            doc_started = time.time()
            status = str(doc.get("status", "ok"))
            text = str(doc.get("text", ""))
            blocks = doc.get("blocks") or []

            hit_terms, candidates = run_gate(text, tx)
            gate_passed = bool(hit_terms)

            call_llm = gate_passed or CALIBRATION_MODE
            if status != "ok":
                call_llm = False

            themes: List[Dict[str, Any]] = []
            violations: List[str] = []
            span_chars = 0
            candidate_theme_codes: List[str] = []
            raw_output = ""

            if call_llm:
                if gate_passed:
                    candidate_theme_codes = list(candidates)
                else:
                    # 較正時、ゲートで落ちた文書は候補を絞れないので全テーマを載せる
                    candidate_theme_codes = [
                        c for c in tx.all_theme_codes if c != OTHER_THEME_CODE
                    ]
                if ALWAYS_INCLUDE_OTHER and OTHER_THEME_CODE in tx.theme_by_code:
                    if OTHER_THEME_CODE not in candidate_theme_codes:
                        candidate_theme_codes.append(OTHER_THEME_CODE)

                spans, _ = build_spans(blocks, tx)
                if not spans:
                    # blocks が無い／ヒットが本文側だけの場合は本文先頭を使う
                    spans = [text[:MAX_TOTAL_SPAN_CHAR_COUNT]] if text else []
                span_text = SPAN_JOINER.join(spans)
                span_chars = len(span_text)

                if span_chars == 0:
                    call_llm = False
                else:
                    if llm is None:
                        llm = load_llm(stage_model())
                    prompt = render_prompt(
                        template,
                        candidate_theme_codes,
                        tx,
                        str(doc.get("title", "")),
                        str(doc.get("source_type", "")),
                        spans,
                    )
                    grammar_text = build_grammar(candidate_theme_codes, tx)
                    try:
                        raw_output = generate_json(llm, prompt, grammar_text)
                        parsed = json.loads(raw_output)
                        themes, violations = validate_themes(
                            parsed, candidate_theme_codes, tx, span_text
                        )
                    except json.JSONDecodeError as e:
                        violations = [f"json_decode:{e}"]
                    except Exception as e:
                        violations = [f"llm_error:{type(e).__name__}:{e}"]

            elapsed = time.time() - doc_started

            base = {
                "document_id": document_id,
                "disclosure_date": doc.get("disclosure_date", ""),
                "code": doc.get("code", ""),
                "company_name": doc.get("company_name", ""),
                "title": doc.get("title", ""),
                "source_type": doc.get("source_type", ""),
                "jpx_sector_17": doc.get("jpx_sector_17", ""),
                "gate_hit_terms": hit_terms,
                "model": model_name,
                "prompt_version": PROMPT_VERSION,
                "taxonomy_version": TAXONOMY_VERSION,
            }

            rows: List[Dict[str, Any]] = []
            if themes:
                for t in themes:
                    row = dict(base)
                    row.update(
                        {
                            "theme_mention_id": _theme_mention_id(
                                document_id, t["theme_code"], t["subtheme_code"], t["evidence_text"]
                            ),
                            "theme_code": t["theme_code"],
                            "subtheme_code": t["subtheme_code"],
                            "direction": t["direction"],
                            "evidence_text": t["evidence_text"],
                            "extraction_confidence": t["extraction_confidence"],
                            "evidence_in_source": t["evidence_in_source"],
                        }
                    )
                    rows.append(row)
            else:
                # 「付かなかった」と「処理していない」を区別するため1行出す（02§5.4）
                row = dict(base)
                row.update(
                    {
                        "theme_mention_id": _theme_mention_id(document_id, None, None, ""),
                        "theme_code": None,
                        "subtheme_code": None,
                        "direction": None,
                        "evidence_text": None,
                        "extraction_confidence": None,
                        "evidence_in_source": None,
                    }
                )
                rows.append(row)

            for row in rows:
                theme_handles[day].write(json.dumps(row, ensure_ascii=False) + "\n")
                if WRITE_CSV:
                    theme_csv_w[day].writerow(_flatten_for_csv(row, THEME_CSV_FIELDS))
            theme_handles[day].flush()
            if WRITE_CSV:
                theme_csv[day].flush()

            runlog_row = {
                "document_id": document_id,
                "disclosure_date": doc.get("disclosure_date", ""),
                "source_type": doc.get("source_type", ""),
                "jpx_sector_17": doc.get("jpx_sector_17", ""),
                "preprocess_status": status,
                "gate_passed": gate_passed,
                "gate_hit_term_count": len(hit_terms),
                "candidate_theme_codes": candidate_theme_codes,
                "candidate_theme_count": len(candidate_theme_codes),
                "llm_called": bool(call_llm),
                "span_chars": span_chars,
                "theme_count": len(themes),
                "schema_violations": violations,
                "elapsed_sec": round(elapsed, 3),
                "model": model_name,
                "prompt_version": PROMPT_VERSION,
                "calibration_mode": CALIBRATION_MODE,
                "raw_output": raw_output if violations else "",
                "processed_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            runlog_handles[day].write(json.dumps(runlog_row, ensure_ascii=False) + "\n")
            runlog_handles[day].flush()
            if WRITE_CSV:
                runlog_csv_w[day].writerow(_flatten_for_csv(runlog_row, RUNLOG_CSV_FIELDS))
                runlog_csv[day].flush()
            processed.add(document_id)

            counters["gate_passed" if gate_passed else "gate_failed"] += 1
            if call_llm:
                counters["llm_called"] += 1
            if themes:
                counters["tagged"] += 1
            if violations:
                counters["violations"] += 1

            total_elapsed = time.time() - started
            eta = (total_elapsed / n) * (len(docs) - n)
            print(
                f"[{n}/{len(docs)}] {document_id} gate={gate_passed} "
                f"cand={len(candidate_theme_codes)} span={span_chars} "
                f"themes={len(themes)} {elapsed:.1f}s eta={eta / 60:.1f}min"
            )
    finally:
        for f in (
            list(theme_handles.values())
            + list(runlog_handles.values())
            + list(theme_csv.values())
            + list(runlog_csv.values())
        ):
            f.close()

    print("\n[done] tagging finished")
    print(f"[done] counters: {dict(counters)}")
    print(f"[done] output  : {_run_dir()}")
    print(f"[done] elapsed : {(time.time() - started) / 60:.1f} min")


# -----------------------------
# 12) レポート（02§9 受入基準）
#     数値が成果物である。「動いた」では受入にならない。
# -----------------------------
def _load_run_outputs() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    run_dir = _run_dir()
    if not os.path.exists(run_dir):
        raise FileNotFoundError(f"run dir not found: {run_dir}")
    themes: List[Dict[str, Any]] = []
    runlog: List[Dict[str, Any]] = []
    days = allowed_days()
    for name in sorted(os.listdir(run_dir)):
        path = os.path.join(run_dir, name)
        m = re.match(r"^(macro_themes|runlog)_(\d{8})\.jsonl$", name)
        if not m:
            continue
        # tag と同じ範囲で集計する。範囲を変えずに report を回せば同じ母数になる。
        if days is not None and m.group(2) not in days:
            continue
        target = themes if m.group(1) == "macro_themes" else runlog
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                target.append(json.loads(line))
    return themes, runlog


@_with_run_log
def report() -> None:
    tx = load_taxonomy()
    theme_rows, runlog = _load_run_outputs()
    if not runlog:
        raise RuntimeError(f"no runlog under {_run_dir()}. tag を先に実行してください。")

    ok_log = [r for r in runlog if r.get("preprocess_status", "ok") == "ok"]
    by_doc_themes: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in theme_rows:
        if row.get("theme_code"):
            by_doc_themes[row["document_id"]].append(row)

    out: Dict[str, Any] = {
        "run_tag": _run_tag(),
        "model": MODEL_PRESETS[MODEL_KEY]["model_name"],
        "prompt_version": PROMPT_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "calibration_mode": CALIBRATION_MODE,
        "document_count": len(runlog),
        "document_count_preprocess_ok": len(ok_log),
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

    print("\n" + "=" * 72)
    print(f"受入基準レポート  run={_run_tag()}  文書数={len(runlog)}（前処理ok={len(ok_log)}）")
    print("=" * 72)

    # (1) source_type別のゲート通過率
    print("\n[1] ゲート通過率（source_type別）  実測基準: timely 34.5 / forecast 50.0 / "
          "earnings 95.9 / presentation 92.6")
    reference = {
        "timely_disclosure": 34.5,
        "forecast_revision": 50.0,
        "earnings": 95.9,
        "earnings_presentation": 92.6,
    }
    gate_by_st: Dict[str, Dict[str, float]] = {}
    for st in sorted({str(r.get("source_type", "")) for r in ok_log}):
        subset = [r for r in ok_log if r.get("source_type") == st]
        passed = sum(1 for r in subset if r.get("gate_passed"))
        rate = passed / len(subset) * 100 if subset else 0.0
        ref = reference.get(st)
        delta = f"{rate - ref:+.1f}pt" if ref is not None else "—"
        gate_by_st[st] = {"n": len(subset), "passed": passed, "rate_pct": round(rate, 1),
                          "reference_pct": ref, "delta_pt": round(rate - ref, 1) if ref is not None else None}
        print(f"    {st:<24} {passed:>4}/{len(subset):<4} {rate:>6.1f}%  "
              f"(基準 {ref if ref is not None else '—'}, {delta})")
    out["gate_pass_rate_by_source_type"] = gate_by_st

    # (2) ゲート通過分のうち実際にテーマが付いた割合（ゲートの誤検出率）
    print("\n[2] ゲート通過分のテーマ付与率（= 1 - ゲート誤検出率）")
    passed_log = [r for r in ok_log if r.get("gate_passed")]
    tagged = sum(1 for r in passed_log if by_doc_themes.get(r["document_id"]))
    tag_rate = tagged / len(passed_log) * 100 if passed_log else 0.0
    print(f"    通過 {len(passed_log)} 件のうち付与あり {tagged} 件 = {tag_rate:.1f}%")
    print(f"    ゲート誤検出率 = {100 - tag_rate:.1f}%")
    out["gate_passed_count"] = len(passed_log)
    out["gate_passed_tagged_count"] = tagged
    out["theme_assign_rate_among_gate_passed_pct"] = round(tag_rate, 1)
    out["gate_false_positive_rate_pct"] = round(100 - tag_rate, 1)

    if CALIBRATION_MODE:
        failed_log = [r for r in ok_log if not r.get("gate_passed")]
        fn = sum(1 for r in failed_log if by_doc_themes.get(r["document_id"]))
        print(f"    [較正] ゲート不通過 {len(failed_log)} 件のうち付与あり {fn} 件 "
              f"= 取りこぼし {fn / len(failed_log) * 100 if failed_log else 0:.1f}%")
        out["gate_false_negative_count"] = fn

    # (3) L1別の付与件数 / (4) L1別のL2 null率 / (5) other率
    print("\n[3][4] L1別の付与件数とL2 null率")
    assigned = [r for r in theme_rows if r.get("theme_code")]
    l1_counter = Counter(r["theme_code"] for r in assigned)
    l1_docs: Dict[str, Set[str]] = defaultdict(set)
    for r in assigned:
        l1_docs[r["theme_code"]].add(r["document_id"])
    l1_stats: Dict[str, Any] = {}
    for code in tx.all_theme_codes:
        rows = [r for r in assigned if r["theme_code"] == code]
        n = len(rows)
        nulls = sum(1 for r in rows if r.get("subtheme_code") is None)
        null_rate = nulls / n * 100 if n else 0.0
        l1_stats[code] = {
            "mentions": n,
            "documents": len(l1_docs.get(code, ())),
            "l2_null": nulls,
            "l2_null_rate_pct": round(null_rate, 1),
        }
        flag = "  ← 付与ゼロ。定義かゲート語彙の問題" if n == 0 else (
            "  ← L2 null率が高い。L2定義の不足" if null_rate >= 50.0 else "")
        print(f"    {code:<24} mentions={n:>4} docs={len(l1_docs.get(code, ())):>4} "
              f"L2null={nulls:>4} ({null_rate:>5.1f}%){flag}")
    out["l1_stats"] = l1_stats

    other_n = l1_counter.get(OTHER_THEME_CODE, 0)
    other_rate = other_n / len(assigned) * 100 if assigned else 0.0
    print(f"\n[5] other率: {other_n}/{len(assigned)} = {other_rate:.1f}%"
          + ("  ← 高い。分類体系の欠落を疑う" if other_rate >= 15.0 else ""))
    out["theme_mention_count"] = len(assigned)
    out["other_rate_pct"] = round(other_rate, 1)

    # (6) GBNF適用下でのスキーマ違反
    print("\n[6] GBNF適用下のスキーマ違反（原則ゼロ。出るなら文法定義の誤り）")
    viol_counter: Counter = Counter()
    viol_docs = 0
    for r in runlog:
        vs = r.get("schema_violations") or []
        if vs:
            viol_docs += 1
        for v in vs:
            viol_counter[str(v).split(":")[0]] += 1
    print(f"    違反のあった文書 {viol_docs} 件 / 種別 {dict(viol_counter) or 'なし'}")
    evidence_missing = sum(1 for r in assigned if r.get("evidence_in_source") is False)
    print(f"    evidence_text が原文に無いもの: {evidence_missing} / {len(assigned)}")
    out["schema_violation_document_count"] = viol_docs
    out["schema_violation_kinds"] = dict(viol_counter)
    out["evidence_not_in_source_count"] = evidence_missing

    # (7) 1件あたり処理時間
    print("\n[7] 処理時間")
    called = [r for r in runlog if r.get("llm_called")]
    times = sorted(float(r.get("elapsed_sec", 0.0)) for r in called)
    if times:
        mean = sum(times) / len(times)
        median = times[len(times) // 2]
        p90 = times[int(len(times) * 0.9) - 1] if len(times) >= 10 else times[-1]
        print(f"    LLM呼出 {len(called)} 件  平均 {mean:.1f}s / 中央 {median:.1f}s / p90 {p90:.1f}s")
        print(f"    合計 {sum(times) / 60:.1f} min")
        print(f"    全市場9,400件への外挿（ゲート通過率61.4%想定）: "
              f"{9400 * 0.614 * mean / 3600:.1f} 時間")
        out["llm_call_count"] = len(called)
        out["seconds_per_document"] = {
            "mean": round(mean, 2), "median": round(median, 2), "p90": round(p90, 2)
        }
    else:
        print("    LLM呼出なし")

    spans = [int(r.get("span_chars", 0)) for r in called if r.get("span_chars")]
    cands = [int(r.get("candidate_theme_count", 0)) for r in called]
    if spans:
        print(f"    スパン平均 {sum(spans) / len(spans):.0f} 字 / 候補L1平均 "
              f"{sum(cands) / len(cands):.1f} 個（設計想定 3.2 + other）")
        out["mean_span_chars"] = round(sum(spans) / len(spans), 1)
        out["mean_candidate_theme_count"] = round(sum(cands) / len(cands), 2)

    report_path = os.path.join(_run_dir(), f"report_{_run_tag()}.json")
    with open(report_path, "w", encoding=OUTPUT_ENCODING) as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[done] metrics: {report_path}")

    # 同じ指標をCSVでも出す。section / key / metric / value の縦持ちにして、
    # ゲート表・L1別表・スカラ指標を1枚で扱えるようにする。
    if WRITE_CSV:
        import csv as _csv

        report_csv_path = os.path.join(_run_dir(), f"report_{_run_tag()}.csv")
        flat: List[Dict[str, Any]] = []
        for section, value in out.items():
            if isinstance(value, dict) and value and all(
                isinstance(v, dict) for v in value.values()
            ):
                for key, metrics in value.items():
                    for metric, mv in metrics.items():
                        flat.append({"section": section, "key": key,
                                     "metric": metric, "value": mv})
            elif isinstance(value, dict):
                for metric, mv in value.items():
                    flat.append({"section": section, "key": "",
                                 "metric": metric, "value": mv})
            else:
                flat.append({"section": "summary", "key": "",
                             "metric": section, "value": value})
        with open(report_csv_path, "w", encoding=CSV_ENCODING, newline="") as f:
            w = _csv.DictWriter(f, fieldnames=["section", "key", "metric", "value"])
            w.writeheader()
            for row in flat:
                w.writerow({k: ("" if row[k] is None else row[k]) for k in row})
        print(f"[done] metrics: {report_csv_path}")

    # 目視確認用。各L1につき3件。数値だけでは誤分類の質が分からない（02§9）。
    sample_path = os.path.join(_run_dir(), f"evidence_samples_{_run_tag()}.md")
    lines: List[str] = [
        f"# 付与結果の目視確認  run={_run_tag()}",
        "",
        f"各L1につき最大3件。`evidence_text` が本当にそのテーマを述べているかを読む。",
        f"生成: {out['generated_at_utc']}",
        "",
    ]
    for code in tx.all_theme_codes:
        t = tx.theme_by_code[code]
        rows = [r for r in assigned if r["theme_code"] == code][:3]
        lines.append(f"## {code}（{t.get('theme_name', '')}）  付与 {l1_counter.get(code, 0)} 件")
        lines.append("")
        lines.append(f"> 定義: {t.get('definition', '')}")
        lines.append("")
        if not rows:
            lines.append("付与ゼロ。定義かゲート語彙の問題を疑う。")
            lines.append("")
            continue
        for r in rows:
            lines.append(f"- **{r.get('company_name', '')}（{r.get('code', '')}）** "
                         f"{r.get('disclosure_date', '')} / {r.get('source_type', '')}")
            lines.append(f"  - タイトル: {r.get('title', '')}")
            lines.append(f"  - L2: `{r.get('subtheme_code')}` / direction: `{r.get('direction')}` "
                         f"/ confidence: {r.get('extraction_confidence')}")
            lines.append(f"  - evidence: 「{r.get('evidence_text', '')}」")
            lines.append(f"  - 原文一致: {r.get('evidence_in_source')}")
            lines.append("")
    with open(sample_path, "w", encoding=OUTPUT_ENCODING) as f:
        f.write("\n".join(lines))
    print(f"[done] samples: {sample_path}")

    if WRITE_CSV:
        import csv as _csv

        sample_csv_path = os.path.join(_run_dir(), f"evidence_samples_{_run_tag()}.csv")
        picked: List[Dict[str, Any]] = []
        for code in tx.all_theme_codes:
            for r in [x for x in assigned if x["theme_code"] == code][:3]:
                picked.append(_flatten_for_csv(r, THEME_CSV_FIELDS))
        with open(sample_csv_path, "w", encoding=CSV_ENCODING, newline="") as f:
            w = _csv.DictWriter(f, fieldnames=list(THEME_CSV_FIELDS), extrasaction="ignore")
            w.writeheader()
            for row in picked:
                w.writerow(row)
        print(f"[done] samples: {sample_csv_path}")


# -----------------------------
# 13) main
# -----------------------------
def main() -> None:
    mode = MODE
    if len(sys.argv) > 1 and sys.argv[1] in ("tag", "report"):
        mode = sys.argv[1]
    if mode == "report":
        report()
    else:
        tag_all()


if __name__ == "__main__":
    main()
