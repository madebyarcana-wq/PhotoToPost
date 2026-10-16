#!/bin/bash
# ドロップ用アプリから呼ばれる。使い方: run.sh <写真フォルダ> [phototopost のオプション...]
REPO="$(cd "$(dirname "$0")/.." && pwd)"
FOLDER="${1%/}"
shift

clear
echo "=== PhotoToPost ==="
echo

if [ ! -d "$FOLDER" ]; then
  echo "フォルダが見つかりません: $FOLDER"
  echo "写真が入った「フォルダ」をドロップしてください（写真ファイル単体ではなく）。"
  exit 1
fi
if [ ! -f "$REPO/.venv/bin/activate" ]; then
  echo "準備ができていません。先にターミナルで次を実行してください:"
  echo "  bash \"$REPO/mac/setup.command\""
  exit 1
fi
source "$REPO/.venv/bin/activate"

# 過去の投稿例（style.txt）があれば、文体の見本として使う
EXTRA=()
if [ -s "$REPO/style.txt" ]; then
  EXTRA+=(--style-file "$REPO/style.txt")
fi

phototopost "$FOLDER" "${EXTRA[@]}" "$@"
STATUS=$?

OUT="${FOLDER}_posts"
if [ -d "$OUT" ] && command -v open >/dev/null 2>&1; then
  open "$OUT"
  [ -f "$OUT/summary.md" ] && open -e "$OUT/summary.md"
fi
echo
echo "終わりました。このウィンドウは閉じて構いません。"
exit $STATUS
