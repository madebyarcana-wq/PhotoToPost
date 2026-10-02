"""Claude による写真の解析と投稿文の作成。

AI の呼び出し方は 2 通り:
- "claude-code"（標準）: Claude Code（claude コマンド）経由。claude.ai の有料プランの範囲で使える。
- "api": Anthropic API を直接呼ぶ。API キーと従量課金が必要。
"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pydantic import BaseModel

from .media import MediaItem
from .platforms import Platform

# 使うモデル。claude-code では未指定ならプランの標準モデル、api では claude-opus-5-5。
MODEL = os.environ.get("PHOTOTOPOST_MODEL")
BACKENDS = ("claude-code", "api")
# Claude Code 1 件あたりの待ち時間の上限（秒）
_CLAUDE_CODE_TIMEOUT = 600
# Claude に送る画像の長辺。これ以上大きくしても精度はほぼ変わらず、料金だけ増える。
_SEND_LONG_EDGE = 1568


class PlatformCaption(BaseModel):
    platform: str
    text: str
    hashtags: list[str]


class Analysis(BaseModel):
    description: str
    subject: str
    focus_x: float
    focus_y: float
    quality_score: int
    quality_notes: str
    highlight_start_seconds: float
    captions: list[PlatformCaption]


class AIError(RuntimeError):
    pass


SYSTEM_PROMPT = """\
あなたは個人の SNS 投稿を手伝うアシスタントです。ユーザーが撮った写真や動画を見て、
投稿用の情報を作ります。

トーン: 個人の日常投稿。自然体で、押しつけがましくなく、本人がその場で感じたことを
書いたような文章にしてください。広告っぽい表現、大げさな形容、決まり文句の多用は避けます。
写真から読み取れないこと（人の名前、店名、具体的な地名など）は作らないでください。
分からないことは、ぼかした表現にします。

各項目の意味:
- description: 何が写っているかを 1〜2 文で。
- subject: 主役になっているもの（短い名詞句）。
- focus_x, focus_y: 主役の中心の位置。画像の左上を (0,0)、右下を (1,1) とする相対座標。
  トリミングの中心に使います。動画の場合は最初に渡した場面で答えてください。
- quality_score: 投稿向きかどうかを 1〜10 で。ピント・ブレ・構図・明るさ・印象で判断。
- quality_notes: 点数の理由を短く。
- highlight_start_seconds: 動画のとき、一番見せたい場面が始まる秒数。写真なら 0。
- captions: 指定された投稿先ごとに 1 つずつ。platform には指定されたキーをそのまま入れます。
  text は本文のみ（ハッシュタグは含めない）、hashtags は # なしの単語のリスト。
"""


@dataclass
class Frame:
    image: Image.Image
    label: str


class CaptionWriter:
    def __init__(
        self, platforms: list[Platform], style_examples: str | None = None, backend: str = "claude-code"
    ):
        if backend not in BACKENDS:
            raise ValueError(f"未対応の AI の呼び出し方です: {backend}")
        self.platforms = platforms
        self.backend = backend
        system = SYSTEM_PROMPT
        if style_examples:
            system += (
                "\n本人の過去の投稿例です。言葉づかい・長さ・絵文字の使い方を参考にしてください"
                "（内容はまねしないこと）。\n<examples>\n" + style_examples.strip() + "\n</examples>\n"
            )
        self.system = system
        if backend == "api":
            import anthropic

            self.client = anthropic.Anthropic()

    def analyze(
        self, item: MediaItem, frames: list[Frame], duration: float | None = None,
        use_location: bool = False, note: str | None = None,
    ) -> Analysis:
        request = self._request_text(item, duration, use_location, note)
        if self.backend == "claude-code":
            return _sanitize(self._via_claude_code(frames, request))
        return _sanitize(self._via_api(frames, request))

    # --- Claude Code（有料プラン）経由 ---------------------------------------
    def _via_claude_code(self, frames: list[Frame], request: str) -> Analysis:
        exe = shutil.which("claude")
        if not exe:
            raise AIError(
                "claude コマンドが見つかりません。Claude Code をインストールし、"
                "一度 claude を起動して claude.ai のアカウントでログインしてください。"
            )
        with tempfile.TemporaryDirectory(prefix="phototopost_") as tmp:
            lines = ["次の画像ファイルを Read ツールで開いて見てください。"]
            for n, frame in enumerate(frames, 1):
                name = f"frame{n}.jpg"
                _downscale(frame.image).save(Path(tmp) / name, "JPEG", quality=85)
                lines.append(f"- {name}: {frame.label}")
            prompt = "\n".join(lines) + "\n\n" + request
            cmd = [
                exe, "-p", prompt,
                "--output-format", "json",
                "--json-schema", json.dumps(Analysis.model_json_schema(), ensure_ascii=False),
                "--append-system-prompt", self.system,
                # 画像を読むことだけを許可する（ファイルの変更やコマンド実行はさせない）
                "--tools", "Read",
                "--allowedTools", "Read",
                "--no-session-persistence",
            ]
            if MODEL:
                cmd += ["--model", MODEL]
            try:
                proc = subprocess.run(
                    cmd, cwd=tmp, capture_output=True, text=True, encoding="utf-8",
                    timeout=_CLAUDE_CODE_TIMEOUT,
                )
            except subprocess.TimeoutExpired as e:
                raise AIError("Claude Code の応答が時間内に返りませんでした。") from e
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            detail = (proc.stderr or proc.stdout).strip()[:300]
            raise AIError(f"Claude Code の実行に失敗しました: {detail}") from e
        if data.get("is_error") or data.get("subtype") != "success":
            # 利用上限に達したとき・ログインが切れたときなどはここに来る
            raise AIError(f"Claude Code がエラーを返しました: {str(data.get('result', ''))[:300]}")
        output = data.get("structured_output")
        if output is None:
            raise AIError("Claude Code の応答を読み取れませんでした。")
        return Analysis.model_validate(output)

    # --- Anthropic API 経由 ----------------------------------------------------
    def _via_api(self, frames: list[Frame], request: str) -> Analysis:
        import anthropic

        content: list[dict] = []
        for frame in frames:
            content.append({"type": "text", "text": frame.label})
            content.append(_image_block(frame.image))
        content.append({"type": "text", "text": "上の画像について。\n" + request})
        try:
            response = self.client.beta.messages.parse(
                model=MODEL or "claude-opus-5-5",
                max_tokens=16000,
                system=self.system,
                messages=[{"role": "user", "content": content}],
                output_config={"effort": "medium"},
                output_format=Analysis,
                # 安全判定で断られたときに、別のモデルで自動的にやり直す
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as e:
            raise AIError("API キーが正しくありません。ANTHROPIC_API_KEY を確認してください。") from e
        except anthropic.RateLimitError as e:
            raise AIError("API の利用上限に達しました。少し待ってから再実行してください。") from e
        except anthropic.APIStatusError as e:
            raise AIError(f"API エラー（{e.status_code}）: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AIError("API に接続できませんでした。ネットワークを確認してください。") from e

        if response.stop_reason == "refusal":
            raise AIError("この写真は AI が処理を断りました。")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise AIError("AI の応答を読み取れませんでした。")
        return response.parsed_output

    def _request_text(
        self, item: MediaItem, duration: float | None, use_location: bool, note: str | None
    ) -> str:
        lines = [("動画（数場面を抜き出したもの）" if item.kind == "video" else "写真") + "について答えてください。"]
        if duration:
            lines.append(f"動画の長さ: {duration:.1f} 秒")
        if item.taken_at:
            lines.append(f"撮影日時: {item.taken_at:%Y年%m月%d日 %H:%M}（季節や時間帯の参考に）")
        if use_location and item.gps:
            lines.append(f"撮影場所の緯度経度: {item.gps[0]}, {item.gps[1]}（おおまかな地域の参考のみ）")
        if note:
            lines.append(f"本人のメモ: {note}")
        lines.append("\n投稿先ごとの書き方:")
        for p in self.platforms:
            limit = f"全角換算で {p.caption_max // 2} 文字以内" if p.weighted_count else f"{p.caption_max} 文字以内"
            lines.append(
                f"- {p.key}（{p.label}）: {p.style_hint} 本文は{limit}。ハッシュタグは最大 {p.hashtags_max} 個。"
            )
        return "\n".join(lines)


def _downscale(img: Image.Image) -> Image.Image:
    img = img.copy()
    img.thumbnail((_SEND_LONG_EDGE, _SEND_LONG_EDGE))
    return img


def _image_block(img: Image.Image) -> dict:
    buf = io.BytesIO()
    _downscale(img).save(buf, format="JPEG", quality=85)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(buf.getvalue()).decode("ascii"),
        },
    }


def _sanitize(a: Analysis) -> Analysis:
    a.focus_x = min(max(a.focus_x, 0.0), 1.0)
    a.focus_y = min(max(a.focus_y, 0.0), 1.0)
    a.quality_score = min(max(a.quality_score, 1), 10)
    a.highlight_start_seconds = max(a.highlight_start_seconds, 0.0)
    return a
