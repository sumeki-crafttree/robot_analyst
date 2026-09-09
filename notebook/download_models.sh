#!/usr/bin/env bash
#
# Gemma 4 の GGUF を Drive の models/ 直下へ取得する（詳細設計 02 §6.3）
#
# Colab での実行:
#   from google.colab import drive; drive.mount('/content/drive')   ← 先にマウントする
#   !bash notebook/download_models.sh                 既定（12b_ud）だけ取得
#   !bash notebook/download_models.sh 12b_ud e4b_ud   複数指定
#   !bash notebook/download_models.sh all             全部
#   !bash notebook/download_models.sh list            一覧だけ表示
#
# 取得先を変えるとき:
#   !MODELS_DIR=/content/models bash notebook/download_models.sh
#
# 取得するのは本体1ファイルだけである。同じリポジトリにある mmproj-*.gguf
# （画像・音声用プロジェクタ）と mtp-*.gguf（Multi-Token Prediction）は
# 本用途では使わないため落とさない。

set -euo pipefail

MODELS_DIR="${MODELS_DIR:-/content/drive/MyDrive/git/prop_candidates/models}"
DEFAULT_KEYS="12b_ud"

# key|HuggingFaceリポジトリ|ファイル名|目安サイズ|用途
CATALOG="
12b_ud|unsloth/gemma-4-12b-it-GGUF|gemma-4-12b-it-UD-Q4_K_XL.gguf|7.4GB|本命。02§6.2 が改良版を優先とする
12b|unsloth/gemma-4-12b-it-GGUF|gemma-4-12b-it-Q4_K_M.gguf|7.1GB|素のQ4_K_M
12b_q8|unsloth/gemma-4-12b-it-GGUF|gemma-4-12b-it-Q8_0.gguf|12.7GB|量子化比較用。T4 16GBにぎりぎり載る
e4b_ud|unsloth/gemma-4-E4B-it-GGUF|gemma-4-E4B-it-UD-Q4_K_XL.gguf|3.5GB|速度比較用
e4b|unsloth/gemma-4-E4B-it-GGUF|gemma-4-E4B-it-Q4_K_M.gguf|3.3GB|速度比較用（素のQ4_K_M）
"

catalog_rows() { printf '%s\n' "$CATALOG" | sed '/^[[:space:]]*$/d'; }

print_catalog() {
  printf '%-10s %-34s %-42s %-8s %s\n' KEY REPO FILE SIZE NOTE
  catalog_rows | while IFS='|' read -r key repo file size note; do
    printf '%-10s %-34s %-42s %-8s %s\n' "$key" "$repo" "$file" "$size" "$note"
  done
}

lookup() {  # $1=key。見つかれば "repo|file|size" を返す
  catalog_rows | awk -F'|' -v k="$1" '$1==k {print $2 "|" $3 "|" $4; exit}'
}

# ---- 引数 ----
if [ "$#" -eq 0 ]; then
  KEYS="$DEFAULT_KEYS"
elif [ "$1" = "list" ]; then
  print_catalog
  exit 0
elif [ "$1" = "all" ]; then
  KEYS="$(catalog_rows | cut -d'|' -f1 | tr '\n' ' ')"
else
  KEYS="$*"
fi

# 先に全キーを検証する。途中で落ちると中途半端な取得が残るため。
for key in $KEYS; do
  if [ -z "$(lookup "$key")" ]; then
    echo "[error] unknown key: $key" >&2
    echo "" >&2
    print_catalog >&2
    exit 2
  fi
done

# ---- ダウンローダの用意 ----
DRY_RUN="${DRY_RUN:-0}"
HF_CMD=""
if [ "$DRY_RUN" != "1" ]; then
  if command -v hf >/dev/null 2>&1; then
    HF_CMD="hf"
  elif command -v huggingface-cli >/dev/null 2>&1; then
    HF_CMD="huggingface-cli"   # 0.34 未満の旧コマンド名
  else
    echo "[info] installing huggingface_hub"
    pip install -q "huggingface_hub[hf_transfer]"
    if command -v hf >/dev/null 2>&1; then HF_CMD="hf"; else HF_CMD="huggingface-cli"; fi
  fi
  # 大きいファイルの転送を速くする。未導入なら無視される。
  export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"
fi

mkdir -p "$MODELS_DIR"
echo "[info] models dir : $MODELS_DIR"
echo "[info] downloader : ${HF_CMD:-(dry-run)}"
echo "[info] targets    : $KEYS"
df -h "$MODELS_DIR" 2>/dev/null | tail -n +1 || true
echo ""

# ---- 取得 ----
downloaded=0
skipped=0
for key in $KEYS; do
  IFS='|' read -r repo file size <<EOF
$(lookup "$key")
EOF
  dest="$MODELS_DIR/$file"

  if [ -f "$dest" ] && [ -s "$dest" ]; then
    echo "[skip] $key : already exists ($(du -h "$dest" | cut -f1)) $dest"
    skipped=$((skipped + 1))
    continue
  fi

  echo "[get ] $key : $repo / $file (~$size)"
  if [ "$DRY_RUN" = "1" ]; then
    echo "       (dry-run) $HF_CMD download $repo $file --local-dir $MODELS_DIR"
  else
    # 途中で切れても同じコマンドで再開する
    "$HF_CMD" download "$repo" "$file" --local-dir "$MODELS_DIR"
    downloaded=$((downloaded + 1))
  fi
done

echo ""
echo "[done] downloaded=$downloaded skipped=$skipped"
echo "[done] contents of $MODELS_DIR:"
ls -lh "$MODELS_DIR" 2>/dev/null | grep -i '\.gguf$' || echo "  (no .gguf found)"
echo ""
echo "[next] tag_macro_theme.py の MODEL_KEY を取得したキーに合わせること。"
echo "       MODEL_KEY = \"${KEYS%% *}\""
