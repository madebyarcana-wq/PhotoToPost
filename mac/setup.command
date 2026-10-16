#!/bin/bash
# PhotoToPost の準備（最初の 1 回だけ）。
# ターミナルで  bash ~/PhotoToPost/mac/setup.command  と入力して実行する。
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"

echo "=== PhotoToPost のセットアップ ==="
echo "場所: $REPO"
echo

# --- 1. Python（3.10 以上）を探す ---
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3 \
         /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
         /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$c" >/dev/null 2>&1 && \
     "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$(command -v "$c")"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "✗ Python 3.10 以上が見つかりません。"
  echo "  https://www.python.org/downloads/ から macOS 用をインストールしてから、もう一度実行してください。"
  exit 1
fi
echo "✓ Python: $("$PY" --version)"

# --- 2. ツール本体をインストール ---
echo "… ツールをインストールしています（1〜2 分かかります）"
"$PY" -m venv "$REPO/.venv" || exit 1
"$REPO/.venv/bin/pip" install -q --upgrade pip >/dev/null 2>&1
if ! "$REPO/.venv/bin/pip" install -q -e "$REPO"; then
  echo "✗ インストールに失敗しました。インターネット接続を確認して、もう一度実行してください。"
  exit 1
fi
echo "✓ ツールをインストールしました"

# --- 3. Claude Code ---
if command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ]; then
  echo "✓ Claude Code は入っています"
else
  echo
  read -r -p "Claude Code が入っていません。今インストールしますか？ [y/N] " ans
  if [[ "$ans" =~ ^[Yy] ]]; then
    curl -fsSL https://claude.ai/install.sh | bash
  else
    echo "  あとで入れる場合: curl -fsSL https://claude.ai/install.sh | bash"
  fi
fi

# --- 4. FFmpeg（動画用・なくても写真は処理できる） ---
if command -v ffmpeg >/dev/null 2>&1; then
  echo "✓ FFmpeg は入っています（動画も処理できます）"
elif command -v brew >/dev/null 2>&1; then
  read -r -p "動画を扱うための FFmpeg を入れますか？ [y/N] " ans
  [[ "$ans" =~ ^[Yy] ]] && brew install ffmpeg
else
  echo "△ FFmpeg がないので、動画はスキップされます（写真は処理できます）"
fi

# --- 5. ドロップ用アプリをデスクトップに作る ---
if ! command -v osacompile >/dev/null 2>&1; then
  echo "△ Mac 以外のため、アプリは作りませんでした。"
  exit 0
fi
APP="$HOME/Desktop/PhotoToPost.app"
TMP="$(mktemp -d)/PhotoToPost.applescript"
# AppleScript の文字列に入れるため、\ と " をエスケープしてから埋め込む
ESCAPED="$(printf '%s' "$REPO" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/[&|]/\\&/g')"
sed "s|__REPO__|$ESCAPED|" "$REPO/mac/PhotoToPost.applescript" > "$TMP"
rm -rf "$APP"
if osacompile -o "$APP" "$TMP"; then
  echo "✓ デスクトップに PhotoToPost.app を作りました"
else
  echo "✗ アプリを作れませんでした"
  exit 1
fi
rm -f "$TMP"
chmod +x "$REPO/mac/run.sh"

echo
echo "=== 準備完了 ==="
echo "まだ Claude にログインしていなければ、このあと  claude  と入力してログインしてください。"
echo "使い方: 写真フォルダをデスクトップの PhotoToPost.app にドラッグ＆ドロップするだけです。"
