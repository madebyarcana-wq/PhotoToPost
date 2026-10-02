"""動画の処理（FFmpeg を使用）。長さの調整・投稿先の比率への切り出し・サムネイル作成。"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .crop import Ratio, crop_box


class FFmpegMissing(RuntimeError):
    pass


@dataclass
class VideoInfo:
    width: int
    height: int
    duration: float
    has_audio: bool


def ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    if not ffmpeg_available():
        raise FFmpegMissing("動画の処理には FFmpeg が必要です（https://ffmpeg.org）")
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def probe(path: Path) -> VideoInfo:
    out = _run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)]
    ).stdout
    data = json.loads(out)
    video = next(s for s in data["streams"] if s.get("codec_type") == "video")
    width, height = int(video["width"]), int(video["height"])
    # スマホ動画は回転情報で縦横が入れ替わっていることがある
    rotation = 0
    for side in video.get("side_data_list", []):
        if "rotation" in side:
            rotation = int(float(side["rotation"]))
    rotation = int(video.get("tags", {}).get("rotate", rotation))
    if abs(rotation) % 180 == 90:
        width, height = height, width
    return VideoInfo(
        width=width,
        height=height,
        duration=float(data["format"].get("duration") or video.get("duration") or 0),
        has_audio=any(s.get("codec_type") == "audio" for s in data["streams"]),
    )


def extract_frame(path: Path, at_seconds: float) -> Image.Image:
    """指定の秒数の 1 コマを画像として取り出す（解析とサムネイル用）。"""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{at_seconds:.2f}", "-i", str(path),
         "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        check=True, capture_output=True,
    ).stdout
    from io import BytesIO

    return Image.open(BytesIO(out)).convert("RGB")


def export_clip(
    src: Path,
    dst: Path,
    info: VideoInfo,
    ratio: Ratio,
    max_seconds: int,
    start: float = 0.0,
    focus: tuple[float, float] = (0.5, 0.5),
    long_edge: int = 1920,
) -> None:
    """比率 ratio で切り出し、max_seconds 以内に収めた MP4 を書き出す。"""
    left, top, right, bottom = crop_box(info.width, info.height, ratio, focus)
    cw, ch = right - left, bottom - top
    scale = min(1.0, long_edge / max(cw, ch))
    # H.264 は幅・高さが偶数である必要がある
    ow, oh = int(cw * scale) // 2 * 2, int(ch * scale) // 2 * 2
    duration = max(0.1, min(max_seconds, info.duration - start))
    vf = f"crop={cw}:{ch}:{left}:{top},scale={ow}:{oh},setsar=1"
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-i", str(src),
           "-t", f"{duration:.2f}", "-vf", vf,
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", "-map_metadata", "-1"]
    cmd += ["-c:a", "aac", "-b:a", "128k"] if info.has_audio else ["-an"]
    cmd.append(str(dst))
    _run(cmd)
