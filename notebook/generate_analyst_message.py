# -*- coding: utf-8 -*-

# ==========================================
# アナリストメッセージ生成（詳細設計 03）
# Colab 1セル貼り付け実行OK
#
#   前処理JSONL → 本文冒頭2,000字 → LLM → 数値検証
#     → analyst_messages_{yyyymmdd}.jsonl（1文書1行）
#
# tag_macro_theme.py とは対象も入力も出力の粒度も異なるため、別スクリプトと
# する（03§3）。ゲートは適用せず、全文書を対象にする。
#
#   LLM実行部（llama-cpp-pythonの初期化、モデルのロード、GBNF、リトライ）は
#   tag_macro_theme.py と重複する。これは意図的である。共通モジュールに切り出すと
#   「Colabに1セル貼り付けて動く」形が壊れるため、重複を許容する。
#   2本を続けて実行するとモデルのロードが2回発生する（各1.5〜6分）。これも許容する。
#
# MODE = "generate" メッセージを生成する（セッション断からの再開に対応）
# MODE = "report"   出力済みJSONLから受入基準（03§8）の数値と目視用サンプルを出す
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
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


def _ensure_dependency(module_name: str, pip_name: Optional[str] = None) -> None:
    try:
        __import__(module_name)
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name or module_name])


# -----------------------------
# 0) 設定（ここだけ編集すればOK）
# -----------------------------
MODE = "generate"  # generate | report

ROOT_DIR = "/content/drive/MyDrive/git/prop_candidates/"


PROCESSED_DIR = ROOT_DIR + "data/processed/"


PREPROCESSED_DIR = PROCESSED_DIR + "tdnet_pdf_preprocessed_02/"


MACRO_LABELED_DIR = PROCESSED_DIR + "macro_labeled/"


SAMPLE_DIR = ROOT_DIR + "data/samples/"


MODEL_DRIVE_DIR = ROOT_DIR + "models/"


LOG_DIR = ROOT_DIR + "log/"


PROMPT_DIR = ROOT_DIR + "data/prompts/"


MODEL_LOCAL_DIR = "/content/models/"


OUTPUT_ENCODING = "utf-8"


LOG_TO_FILE = True


SCRIPT_NAME = "generate_analyst_message"


LOG_CAPTURE_NATIVE_STDERR = True


WRITE_CSV = True


CSV_ENCODING = "utf-8-sig"  # BOM付き。Excelで開いたときに日本語が化けないようにする。




# 出力先の階層 <run_tag>/<公開日>/ をテーマ付与と揃えるために使う。
# 分離の前後で出力パスを変えないためであり、v1 はマクロテーマ側の版を指す。
# メッセージ自体の版は MESSAGE_PROMPT_VERSION に記録される。
PROMPT_VERSION = "v1"


USE_BODIES_SAMPLE = False


BODIES_SAMPLE_JSONL = SAMPLE_DIR + "tdnet_bodies_202608.jsonl"


START_DATE = "2026-09-07"  # YYYY-MM-DD または YYYYMMDD


END_DATE = "2026-09-07"


MAX_DOCUMENTS: Optional[int] = None


CONTEXT_DIR = ROOT_DIR + "data/context/"


MESSAGE_PROMPT_VERSION = "analyst_message_v1"


MESSAGE_CONTEXT_VERSION = "hedge_fund_analyst_v1"


MESSAGE_PROMPT_PATH = PROMPT_DIR + f"{MESSAGE_PROMPT_VERSION}.txt"


MESSAGE_CONTEXT_PATH = CONTEXT_DIR + f"{MESSAGE_CONTEXT_VERSION}.md"


MESSAGE_BODY_CHARS = 2000


MESSAGE_LEAD_CHARS = 200  # 「記」の手前から何字さかのぼるか


MESSAGE_MIN_CHARS = 40


MESSAGE_MAX_CHARS = 80


MESSAGE_GRAMMAR_MAX_CHARS = 160  # 文法上の上限。40〜80字はプロンプトで指示する


MESSAGE_MAX_OUTPUT_TOKENS = 256


MESSAGE_SKIP_ISSUER_KINDS: List[str] = ["etf_etn", "reit_fund"]


MESSAGE_MATERIALITY_VALUES: List[str] = ["high", "medium", "low", "none"]


MESSAGE_SAMPLES_PER_MATERIALITY = 5  # 目視確認用に materiality 別で書き出す件数


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


N_GPU_LAYERS = -1


REQUIRE_GPU = True


N_BATCH = 512


MAX_OUTPUT_TOKENS = 512


TEMPERATURE = 0.0  # 再現性のため（01§6.1）


LLAMA_CPP_WHEEL_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/cu124"


def _run_tag() -> str:
    return f"{MODEL_PRESETS[MODEL_KEY]['model_name']}__{PROMPT_VERSION}"


def _run_dir() -> str:
    return os.path.join(MACRO_LABELED_DIR, _run_tag())


def _day_dir(day: str) -> str:
    """公開日ごとの出力フォルダ。<MACRO_LABELED_DIR>/<run_tag>/yyyymmdd/"""
    return os.path.join(_run_dir(), day)


def _log_path() -> str:
    """<LOG_DIR>/<日時>_<スクリプト名>__<run_tag>.txt

    日時を先頭に置き、Driveの名前順が実行順になるようにする。
    run_tag（モデル名とプロンプト版）まで入れて、開かずに区別できるようにする。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(LOG_DIR, f"{stamp}_{SCRIPT_NAME}__{_run_tag()}.txt")


def _log_header() -> str:
    """ログ先頭に残す実行条件。スクリプトごとに中身が変わる。"""
    return (
        f"model={MODEL_KEY} prompt={MESSAGE_PROMPT_VERSION} "
        f"context={MESSAGE_CONTEXT_VERSION} dates={START_DATE or '-'}..{END_DATE or '-'}"
    )


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

    if not os.path.exists(PREPROCESSED_DIR):
        raise FileNotFoundError(
            f"preprocessed dir not found: {PREPROCESSED_DIR}\n"
            "preprocess_disclosures.py を先に実行してください。"
        )
    # <PREPROCESSED_DIR>/yyyymmdd/disclosures_yyyymmdd.jsonl
    day_pattern = re.compile(r"^(\d{8})$")
    matched: List[Tuple[str, str]] = []
    for name in sorted(os.listdir(PREPROCESSED_DIR)):
        if not day_pattern.match(name):
            continue
        path = os.path.join(PREPROCESSED_DIR, name, f"disclosures_{name}.jsonl")
        if os.path.exists(path):
            matched.append((name, path))
    if not matched:
        raise RuntimeError(
            f"no yyyymmdd/disclosures_yyyymmdd.jsonl under: {PREPROCESSED_DIR}\n"
            "preprocess_disclosures.py を先に実行してください。"
        )
    paths = [path for day, path in matched if days is None or day in days]
    if not paths:
        raise RuntimeError(
            f"no disclosures file in range {START_DATE}..{END_DATE} under: {PREPROCESSED_DIR}\n"
            f"存在するのは {sorted(d for d, _ in matched)} です。"
        )
    for path in paths:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    print(f"[info] documents from processed: {len(docs)} files={len(paths)}"
          + (f" days={START_DATE}..{END_DATE}" if days is not None else ""))
    return docs


_GBNF_NAME_RE = re.compile(r"^[A-Za-z0-9-]+$")


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


GEMMA_TURN_TEMPLATE = "<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"


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


def generate_json(
    llm, prompt: str, grammar_text: str, max_tokens: Optional[int] = None
) -> str:
    from llama_cpp import LlamaGrammar  # type: ignore

    grammar = LlamaGrammar.from_string(grammar_text, verbose=False)
    out = llm.create_completion(
        prompt=GEMMA_TURN_TEMPLATE.format(prompt=prompt),
        grammar=grammar,
        temperature=TEMPERATURE,
        max_tokens=MAX_OUTPUT_TOKENS if max_tokens is None else max_tokens,
        stop=["<end_of_turn>"],
    )
    return out["choices"][0]["text"]


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


def load_message_prompt_template() -> str:
    if not os.path.exists(MESSAGE_PROMPT_PATH):
        raise FileNotFoundError(
            f"message prompt not found: {MESSAGE_PROMPT_PATH}\n"
            f"リポジトリの data/prompts/{MESSAGE_PROMPT_VERSION}.txt を"
            f" {PROMPT_DIR} へアップロードすること。"
        )
    print(f"[info] message prompt : {MESSAGE_PROMPT_PATH}")
    with open(MESSAGE_PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def load_analyst_context() -> str:
    """読み手の定義と品質基準。プロンプトへ実行時に差し込む（03§4）。

    読み手を切り替える場合はこのファイルを差し替える。プロンプトは変えない。
    """
    if not os.path.exists(MESSAGE_CONTEXT_PATH):
        raise FileNotFoundError(
            f"analyst context not found: {MESSAGE_CONTEXT_PATH}\n"
            f"リポジトリの data/context/{MESSAGE_CONTEXT_VERSION}.md を"
            f" {CONTEXT_DIR} へアップロードすること。"
        )
    print(f"[info] message context: {MESSAGE_CONTEXT_PATH}")
    with open(MESSAGE_CONTEXT_PATH, encoding="utf-8") as f:
        return f.read()


def message_body_excerpt(text: str) -> str:
    """本文の冒頭を切り出す（03§6.1）。

    適時開示は定型で「記」の直後に理由・内容・日程が並ぶ。「記」があれば
    その手前から始め、無ければ先頭から MESSAGE_BODY_CHARS 字を取る。
    """
    body = str(text or "").strip()
    if not body:
        return ""
    head = body[: MESSAGE_BODY_CHARS * 2]
    match = re.search(r"(?:^|\n)\s*記\s*(?:\n|$)", head)
    if match:
        start = max(0, match.start() - MESSAGE_LEAD_CHARS)
        return body[start : start + MESSAGE_BODY_CHARS]
    return body[:MESSAGE_BODY_CHARS]


def render_message_prompt(template: str, context: str, doc: Dict[str, Any], body: str) -> str:
    out = template
    for key, value in (
        ("{{ANALYST_CONTEXT}}", context),
        ("{{COMPANY_NAME}}", str(doc.get("company_name", "") or "")),
        ("{{JPX_SECTOR_17}}", str(doc.get("jpx_sector_17", "") or "")),
        ("{{SOURCE_TYPE}}", str(doc.get("source_type", "") or "")),
        ("{{DOCUMENT_TITLE}}", str(doc.get("title", "") or "")),
        ("{{BODY}}", body),
        ("{{MIN_CHARS}}", str(MESSAGE_MIN_CHARS)),
        ("{{MAX_CHARS}}", str(MESSAGE_MAX_CHARS)),
    ):
        out = out.replace(key, value)
    return out


def build_message_grammar() -> str:
    """1文書1行のメッセージ用。既存のテーマ用文法とは別物である。

    規則名に使えるのは英数字とハイフンのみ（_validate_gbnf）。
    """
    alts = " | ".join('"\\"%s\\""' % v for v in MESSAGE_MATERIALITY_VALUES)
    lines = [
        'root ::= "{" ws "\\"analyst_message\\"" ws ":" ws msg ws ","'
        ' ws "\\"message_materiality\\"" ws ":" ws materiality ws "}"',
        'msg ::= "\\"" msgchar{1,%d} "\\""' % MESSAGE_GRAMMAR_MAX_CHARS,
        r'msgchar ::= [^"\\\n\r\t] | "\\" ["\\/bfnrt]',
        "materiality ::= " + alts,
        "ws ::= [ \\t\\n]*",
    ]
    text = "\n".join(lines) + "\n"
    _validate_gbnf(text)
    return text


_SCALE_UNITS: Dict[str, int] = {"兆": 10 ** 12, "億": 10 ** 8, "百万": 10 ** 6, "万": 10 ** 4, "千": 10 ** 3}


_SCALE_ALT = "|".join(_SCALE_UNITS)


_NUM = r"\d[\d,]*(?:\.\d+)?"


_QUANTITY_RE = re.compile(
    rf"((?:{_NUM}\s*(?:{_SCALE_ALT})\s*)*{_NUM}\s*(?:{_SCALE_ALT})?)\s*(円|株)"
)


_PERCENT_RE = re.compile(rf"({_NUM})\s*(?:%|パーセント)")


_PERIOD_RE = re.compile(rf"(?:第)?({_NUM})\s*(?:Q|四半期)")


_DATE_RE = re.compile(rf"({_NUM})\s*(年|月|日)")


_BARE_RE = re.compile(rf"({_NUM})\s*(倍|ポイント|件|名|人|回|拠点|店)")


def _to_number(raw: str) -> Optional[float]:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _quantity_value(chunk: str) -> Optional[float]:
    """「1億2,000万」→ 120000000。単位の連鎖を足し合わせる。"""
    total = 0.0
    found = False
    for num, scale in re.findall(rf"({_NUM})\s*({_SCALE_ALT})?", chunk):
        value = _to_number(num)
        if value is None:
            continue
        total += value * (_SCALE_UNITS.get(scale, 1) if scale else 1)
        found = True
    return total if found else None


def number_tokens(text: str) -> Set[str]:
    """比較用に正規化した数値表現の集合を返す。"""
    src = _normalize_text(text)
    tokens: Set[str] = set()
    for chunk, unit in _QUANTITY_RE.findall(src):
        value = _quantity_value(chunk)
        if value is not None:
            tokens.add(f"{'money' if unit == '円' else 'share'}:{value:.4g}")
    for pattern, label in ((_PERCENT_RE, "pct"), (_PERIOD_RE, "period")):
        for num in pattern.findall(src):
            value = _to_number(num)
            if value is not None:
                tokens.add(f"{label}:{value:.4g}")
    for num, unit in _DATE_RE.findall(src):
        value = _to_number(num)
        if value is not None:
            tokens.add(f"{unit}:{value:.4g}")
    for num, unit in _BARE_RE.findall(src):
        value = _to_number(num)
        if value is not None:
            tokens.add(f"{unit}:{value:.4g}")
    return tokens


def verify_message_numbers(message: str, source_text: str) -> Tuple[bool, List[str]]:
    """メッセージ中の数値がすべて原文に存在するか。"""
    in_message = number_tokens(message)
    if not in_message:
        return True, []  # 数値を含まないメッセージは検証対象がない
    in_source = number_tokens(source_text)
    missing = sorted(in_message - in_source)
    return not missing, missing


def _messages_path(day: str) -> str:
    return os.path.join(_day_dir(day), f"analyst_messages_{day}.jsonl")


def _messages_csv_path(day: str) -> str:
    return os.path.join(_day_dir(day), f"analyst_messages_{day}.csv")


MESSAGE_CSV_FIELDS: Sequence[str] = (
    "document_id",
    "disclosure_date",
    "code",
    "company_name",
    "title",
    "source_type",
    "jpx_sector_17",
    "issuer_kind",
    "analyst_message",
    "message_materiality",
    "message_numbers_verified",
    "message_char_count",
    "message_title_overlap",
    "message_regenerated",
    "message_model",
    "prompt_version",
    "context_version",
    "elapsed_sec",
    "status",
    "error",
)


def load_processed_message_ids() -> Set[str]:
    """再開用。処理済みの document_id を集める（02§8.3）。"""
    done: Set[str] = set()
    run_dir = _run_dir()
    if not os.path.exists(run_dir):
        return done
    for day in sorted(os.listdir(run_dir)):
        path = os.path.join(run_dir, day, f"analyst_messages_{day}.jsonl")
        if not re.match(r"^\d{8}$", day) or not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["document_id"])
            except Exception:
                continue
    return done


def select_message_targets(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """メッセージ生成の対象（03§3・§6.4）。

    ゲートも source_type も業種も見ない。全文書が対象である。除くのは
    メッセージが成立しないものだけ。
    """
    kept: List[Dict[str, Any]] = []
    excluded: Counter = Counter()
    for doc in docs:
        kind = str(doc.get("issuer_kind", "") or "")
        if kind in MESSAGE_SKIP_ISSUER_KINDS:
            excluded[f"issuer_kind={kind}"] += 1
            continue
        if not message_body_excerpt(doc.get("text", "")):
            excluded["empty_body"] += 1
            continue
        kept.append(doc)
    print(f"[info] message targets: {len(kept)} / {len(docs)} (excluded={len(docs) - len(kept)})")
    for reason, count in excluded.most_common():
        print(f"[info]   excluded {reason}: {count}")
    return kept


def _title_overlap(message: str, title: str) -> float:
    """タイトルの言い換えかどうかの目安。文字bigramのJaccard係数。"""
    def bigrams(value: str) -> Set[str]:
        v = re.sub(r"\s+", "", _normalize_text(value))
        return {v[i : i + 2] for i in range(len(v) - 1)}

    a, b = bigrams(message), bigrams(title)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def generate_analyst_message(
    llm: Any, doc: Dict[str, Any], template: str, context: str, grammar_text: str
) -> Dict[str, Any]:
    """1文書1件のメッセージを作る。数値が原文になければ1回だけ作り直す。"""
    body = message_body_excerpt(doc.get("text", ""))
    prompt = render_message_prompt(template, context, doc, body)
    source_text = str(doc.get("text", "") or "")

    message = ""
    materiality = ""
    verified = False
    missing: List[str] = []
    regenerated = False
    error = ""

    for attempt in range(2):
        try:
            raw = generate_json(
                llm, prompt, grammar_text, max_tokens=MESSAGE_MAX_OUTPUT_TOKENS
            )
            parsed = json.loads(raw)
            message = str(parsed.get("analyst_message", "") or "").strip()
            materiality = str(parsed.get("message_materiality", "") or "").strip()
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            break

        verified, missing = verify_message_numbers(message, source_text)
        if verified:
            break
        if attempt == 0:
            # 原文にない数値が含まれている。1回だけ作り直す（03§6.3）。
            regenerated = True

    return {
        "analyst_message": message,
        "message_materiality": materiality,
        "message_numbers_verified": verified,
        "message_numbers_missing": missing,
        "message_char_count": len(message),
        "message_title_overlap": round(_title_overlap(message, str(doc.get("title", ""))), 3),
        "message_regenerated": regenerated,
        "error": error,
    }


def run_message_pass(docs: List[Dict[str, Any]], llm: Any) -> Any:
    """アナリストメッセージを生成する（設計03）。

    テーマ付与と同じ実行内で回す。モデルのロードに3〜7分かかるため、
    プロセスを分けない（03§3）。llm が未ロードならここで読む。
    """
    template = load_message_prompt_template()
    context = load_analyst_context()
    grammar_text = build_message_grammar()

    targets = select_message_targets(docs)
    if MAX_DOCUMENTS is not None and MAX_DOCUMENTS > 0:
        targets = targets[:MAX_DOCUMENTS]
    processed = load_processed_message_ids()
    print(f"[info] messages already processed: {len(processed)} / {len(targets)}")

    model_name = MODEL_PRESETS[MODEL_KEY]["model_name"]
    handles: Dict[str, Any] = {}
    csv_handles: Dict[str, Any] = {}
    csv_writers: Dict[str, Any] = {}
    counters: Counter = Counter()
    started = time.time()

    try:
        for n, doc in enumerate(targets, 1):
            document_id = str(doc.get("document_id", ""))
            if document_id in processed:
                counters["skipped_done"] += 1
                continue

            day = _date_to_compact(doc.get("disclosure_date", ""))
            if day not in handles:
                os.makedirs(_day_dir(day), exist_ok=True)
                handles[day] = open(_messages_path(day), "a", encoding=OUTPUT_ENCODING)
                if WRITE_CSV:
                    csv_handles[day], csv_writers[day] = open_csv_appender(
                        _messages_csv_path(day), MESSAGE_CSV_FIELDS
                    )

            if llm is None:
                llm = load_llm(stage_model())

            doc_started = time.time()
            result = generate_analyst_message(llm, doc, template, context, grammar_text)
            elapsed = time.time() - doc_started

            row = {
                "document_id": document_id,
                "disclosure_date": str(doc.get("disclosure_date", "")),
                "code": str(doc.get("code", "")),
                "company_name": str(doc.get("company_name", "")),
                "title": str(doc.get("title", "")),
                "source_type": str(doc.get("source_type", "")),
                "jpx_sector_17": str(doc.get("jpx_sector_17", "")),
                "issuer_kind": str(doc.get("issuer_kind", "")),
                "message_model": model_name,
                "prompt_version": MESSAGE_PROMPT_VERSION,
                "context_version": MESSAGE_CONTEXT_VERSION,
                "elapsed_sec": round(elapsed, 3),
                "status": "failed" if result["error"] else "ok",
                "processed_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                **result,
            }
            handles[day].write(json.dumps(row, ensure_ascii=False) + "\n")
            handles[day].flush()
            if WRITE_CSV:
                csv_writers[day].writerow(_flatten_for_csv(row, MESSAGE_CSV_FIELDS))
                csv_handles[day].flush()
            processed.add(document_id)

            counters[row["status"]] += 1
            if not result["message_numbers_verified"]:
                counters["numbers_unverified"] += 1
            if result["message_regenerated"]:
                counters["regenerated"] += 1
            counters[f"materiality_{result['message_materiality'] or 'blank'}"] += 1

            total_elapsed = time.time() - started
            eta = (total_elapsed / n) * (len(targets) - n)
            print(
                f"[msg {n}/{len(targets)}] {document_id} "
                f"mat={result['message_materiality']} chars={result['message_char_count']} "
                f"num_ok={result['message_numbers_verified']} "
                f"{elapsed:.1f}s eta={eta / 60:.1f}min"
            )
    finally:
        for f in list(handles.values()) + list(csv_handles.values()):
            f.close()

    print("\n[done] analyst messages finished")
    print(f"[done] counters: {dict(counters)}")
    print(f"[done] elapsed : {(time.time() - started) / 60:.1f} min")
    return llm


def _load_message_outputs() -> List[Dict[str, Any]]:
    run_dir = _run_dir()
    rows: List[Dict[str, Any]] = []
    if not os.path.exists(run_dir):
        return rows
    days = allowed_days()
    for day in sorted(os.listdir(run_dir)):
        if not re.match(r"^\d{8}$", day):
            continue
        if days is not None and day not in days:
            continue
        path = os.path.join(run_dir, day, f"analyst_messages_{day}.jsonl")
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def message_report() -> None:
    """受入基準の数値を出す（03§8）。数値だけでは測れないため目視用も書く。"""
    rows = _load_message_outputs()
    if not rows:
        print("[info] no analyst messages found. 先に generate を実行すること。")
        return

    ok = [r for r in rows if r.get("status") == "ok" and r.get("analyst_message")]
    total = len(rows)
    unverified = [r for r in ok if not r.get("message_numbers_verified")]
    lengths = [int(r.get("message_char_count") or 0) for r in ok]
    in_range = [n for n in lengths if MESSAGE_MIN_CHARS <= n <= MESSAGE_MAX_CHARS]
    overlaps = [float(r.get("message_title_overlap") or 0.0) for r in ok]
    elapsed = [float(r.get("elapsed_sec") or 0.0) for r in rows]
    materiality = Counter(str(r.get("message_materiality") or "blank") for r in ok)

    def pct(part: int, whole: int) -> float:
        return round(part / whole * 100, 1) if whole else 0.0

    def quantiles(values: List[float]) -> Dict[str, float]:
        if not values:
            return {}
        ordered = sorted(values)
        def q(p: float) -> float:
            return round(ordered[min(len(ordered) - 1, int(p * len(ordered)))], 2)
        return {"min": round(ordered[0], 2), "p25": q(0.25), "median": q(0.5),
                "p75": q(0.75), "max": round(ordered[-1], 2)}

    summary = {
        "run_tag": _run_tag(),
        "model": MODEL_PRESETS[MODEL_KEY]["model_name"],
        "prompt_version": MESSAGE_PROMPT_VERSION,
        "context_version": MESSAGE_CONTEXT_VERSION,
        "documents": total,
        "generated": len(ok),
        "failed": total - len(ok),
        "numbers_unverified": len(unverified),
        "numbers_unverified_pct": pct(len(unverified), len(ok)),
        "regenerated": sum(1 for r in ok if r.get("message_regenerated")),
        "materiality": dict(materiality),
        "materiality_pct": {k: pct(v, len(ok)) for k, v in materiality.items()},
        "char_count": quantiles([float(n) for n in lengths]),
        "char_count_in_range_pct": pct(len(in_range), len(ok)),
        "title_overlap": quantiles(overlaps),
        "title_overlap_over_50pct": pct(sum(1 for v in overlaps if v >= 0.5), len(ok)),
        "elapsed_sec_per_document": quantiles(elapsed),
    }

    print("\n===== analyst message report =====")
    print(f"documents={total} generated={len(ok)} failed={total - len(ok)}")
    print(f"numbers_unverified: {len(unverified)} ({summary['numbers_unverified_pct']}%)"
          f" / regenerated: {summary['regenerated']}")
    print(f"materiality: {summary['materiality_pct']}")
    print(f"char_count: {summary['char_count']} in {MESSAGE_MIN_CHARS}-{MESSAGE_MAX_CHARS}"
          f"字: {summary['char_count_in_range_pct']}%")
    print(f"title_overlap: {summary['title_overlap']}"
          f" (>=0.5 は {summary['title_overlap_over_50pct']}%)")
    print(f"elapsed_sec/doc: {summary['elapsed_sec_per_document']}")

    report_path = os.path.join(_run_dir(), f"message_report_{_run_tag()}.json")
    with open(report_path, "w", encoding=OUTPUT_ENCODING) as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[done] message metrics: {report_path}")

    # 目視用。数値だけでは品質を測れない（03§8）。
    sample_path = os.path.join(_run_dir(), f"message_samples_{_run_tag()}.md")
    with open(sample_path, "w", encoding=OUTPUT_ENCODING) as f:
        f.write(f"# アナリストメッセージ 目視確認\n\n")
        f.write(f"- model: {summary['model']}\n- prompt: {MESSAGE_PROMPT_VERSION}\n")
        f.write(f"- context: {MESSAGE_CONTEXT_VERSION}\n\n")
        f.write("確認する点\n\n")
        f.write("- タイトルを言い換えただけになっていないか\n")
        f.write("- 本文にない解釈を足していないか\n")
        f.write("- 「影響は軽微」を無理に意味のある話にしていないか\n\n")
        for value in MESSAGE_MATERIALITY_VALUES:
            picked = [r for r in ok if r.get("message_materiality") == value][:MESSAGE_SAMPLES_PER_MATERIALITY]
            f.write(f"\n## {value}（{materiality.get(value, 0)}件中 {len(picked)}件）\n\n")
            if not picked:
                f.write("該当なし\n")
                continue
            for r in picked:
                f.write(f"### {r.get('company_name')}（{r.get('code')}）\n\n")
                f.write(f"- タイトル: {r.get('title')}\n")
                f.write(f"- メッセージ: **{r.get('analyst_message')}**\n")
                f.write(f"- 文字数: {r.get('message_char_count')} / "
                        f"タイトル重複: {r.get('message_title_overlap')} / "
                        f"数値検証: {r.get('message_numbers_verified')}")
                if r.get("message_numbers_missing"):
                    f.write(f" (原文に無い数値: {r['message_numbers_missing']})")
                f.write("\n\n")
    print(f"[done] message samples: {sample_path}")


@_with_run_log
def report() -> None:
    """受入基準の数値と目視用サンプルを出す（03§8）。LLMを読み込まない。"""
    message_report()



# -----------------------------
# main
# -----------------------------
@_with_run_log
def generate_all() -> None:
    assert_gpu_available()
    run_message_pass(load_documents(), llm=None)


def main() -> None:
    mode = MODE
    if len(sys.argv) > 1 and sys.argv[1] in ("generate", "report"):
        mode = sys.argv[1]
    if mode == "report":
        report()
    else:
        generate_all()


if __name__ == "__main__":
    main()
