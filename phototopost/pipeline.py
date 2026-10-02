"""1 件ずつ写真・動画を処理して、出力フォルダに書き出す。"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import video as vid
from .ai import AIError, Analysis, CaptionWriter, Frame
from .crop import choose_ratio, crop_and_resize, estimate_focus
from .enhance import auto_enhance, sharpen_for_web
from .media import MediaItem, load_photo
from .platforms import Platform
from .textutil import compose, count_chars, normalize_hashtags


@dataclass
class Options:
    platforms: list[Platform]
    strength: float = 0.7
    use_ai: bool = True
    use_location: bool = False
    style_examples: str | None = None


@dataclass
class PostResult:
    source: str
    kind: str
    folder: str
    subject: str = ""
    description: str = ""
    quality_score: int | None = None
    quality_notes: str = ""
    files: dict[str, str] = field(default_factory=dict)
    captions: dict[str, str] = field(default_factory=dict)
    error: str | None = None


class Pipeline:
    def __init__(self, options: Options, out_dir: Path):
        self.opt = options
        self.out_dir = out_dir
        self.writer = CaptionWriter(options.platforms, options.style_examples) if options.use_ai else None

    def process(self, item: MediaItem) -> PostResult:
        folder = self.out_dir / _folder_name(item)
        folder.mkdir(parents=True, exist_ok=True)
        result = PostResult(source=str(item.path), kind=item.kind, folder=str(folder))
        try:
            if item.kind == "photo":
                self._photo(item, folder, result)
            else:
                self._video(item, folder, result)
        except (AIError, vid.FFmpegMissing, OSError, ValueError) as e:
            result.error = str(e)
        except subprocess.CalledProcessError as e:
            result.error = f"FFmpeg の処理に失敗しました: {(e.stderr or '').strip()[:300]}"
        _write_post_md(folder, item, result, self.opt.platforms)
        return result

    # --- 写真 ---------------------------------------------------------------
    def _photo(self, item: MediaItem, folder: Path, result: PostResult) -> None:
        img = load_photo(item)
        analysis = self._analyze(item, [Frame(img, "写真:")])
        focus = (analysis.focus_x, analysis.focus_y) if analysis else estimate_focus(img)
        enhanced = auto_enhance(img, self.opt.strength)
        for p in self.opt.platforms:
            ratio = choose_ratio(img.width, img.height, p.photo_ratios)
            out = crop_and_resize(enhanced, ratio, p.photo_long_edge, focus)
            out = sharpen_for_web(out, self.opt.strength)
            path = folder / f"{p.key}.jpg"
            # 撮影場所などの情報（EXIF）は付けずに保存する
            out.save(path, "JPEG", quality=92, optimize=True, progressive=True)
            result.files[p.key] = path.name
        self._fill_text(item, analysis, result)

    # --- 動画 ---------------------------------------------------------------
    def _video(self, item: MediaItem, folder: Path, result: PostResult) -> None:
        info = vid.probe(item.path)
        times = [info.duration * t for t in (0.1, 0.5, 0.85)] if info.duration > 1 else [0.0]
        frames = [Frame(vid.extract_frame(item.path, t), f"{t:.1f} 秒の場面:") for t in times]
        analysis = self._analyze(item, frames, duration=info.duration)
        focus = (analysis.focus_x, analysis.focus_y) if analysis else (0.5, 0.5)
        for p in self.opt.platforms:
            start = 0.0
            if analysis and info.duration > p.video_max_seconds:
                start = min(analysis.highlight_start_seconds, info.duration - p.video_max_seconds)
            path = folder / f"{p.key}.mp4"
            vid.export_clip(item.path, path, info, p.video_ratio, p.video_max_seconds, start, focus)
            result.files[p.key] = path.name
        # サムネイル（カバー画像）は見どころの場面から作る
        thumb_t = analysis.highlight_start_seconds if analysis else times[len(times) // 2]
        thumb = auto_enhance(vid.extract_frame(item.path, min(thumb_t, max(info.duration - 0.1, 0))), self.opt.strength)
        for p in self.opt.platforms:
            out = crop_and_resize(thumb, p.video_ratio, p.photo_long_edge, focus)
            out.save(folder / f"{p.key}_cover.jpg", "JPEG", quality=90)
        self._fill_text(item, analysis, result)

    # --- 共通 ---------------------------------------------------------------
    def _analyze(self, item: MediaItem, frames: list[Frame], duration: float | None = None) -> Analysis | None:
        if not self.writer:
            return None
        return self.writer.analyze(
            item, frames, duration=duration, use_location=self.opt.use_location, note=_read_note(item)
        )

    def _fill_text(self, item: MediaItem, analysis: Analysis | None, result: PostResult) -> None:
        if analysis:
            result.subject = analysis.subject
            result.description = analysis.description
            result.quality_score = analysis.quality_score
            result.quality_notes = analysis.quality_notes
        by_key = {c.platform.lower(): c for c in analysis.captions} if analysis else {}
        for p in self.opt.platforms:
            c = by_key.get(p.key)
            if c:
                tags = normalize_hashtags(c.hashtags, p.hashtags_max)
                result.captions[p.key] = compose(c.text, tags, p.caption_max, p.weighted_count)
            else:
                result.captions[p.key] = _placeholder(item)


def _folder_name(item: MediaItem) -> str:
    stem = re.sub(r"[^\w\-]+", "_", item.path.stem)
    return f"{item.kind}_{stem}"


def _read_note(item: MediaItem) -> str | None:
    """写真と同じ名前の .txt があれば、本人のメモとして AI に渡す（例: IMG_0001.txt）。"""
    note = item.path.with_suffix(".txt")
    if note.exists():
        return note.read_text(encoding="utf-8").strip() or None
    return None


def _placeholder(item: MediaItem) -> str:
    when = f"{item.taken_at.month}月{item.taken_at.day}日の" if item.taken_at else ""
    return f"{when}一枚。（ここに投稿文を書いてください）"


def _write_post_md(folder: Path, item: MediaItem, r: PostResult, platforms: list[Platform]) -> None:
    lines = [f"# {item.path.name}", ""]
    if r.error:
        lines += [f"**エラー:** {r.error}", ""]
    if r.description:
        lines += [f"- 写っているもの: {r.description}"]
    if r.quality_score is not None:
        lines += [f"- 投稿向き度: {r.quality_score}/10（{r.quality_notes}）"]
    if item.taken_at:
        lines += [f"- 撮影日時: {item.taken_at:%Y-%m-%d %H:%M}"]
    lines.append("")
    for p in platforms:
        text = r.captions.get(p.key)
        if text is None:
            continue
        n = count_chars(text, p.weighted_count)
        lines += [f"## {p.label}", "", f"画像/動画: `{r.files.get(p.key, '-')}`　文字数: {n}/{p.caption_max}", "", text, ""]
        if p.notes:
            lines += [f"> {' '.join(p.notes)}", ""]
    (folder / "post.md").write_text("\n".join(lines), encoding="utf-8")


def write_summary(out_dir: Path, results: list[PostResult]) -> Path:
    (out_dir / "results.json").write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ranked = sorted(results, key=lambda r: -(r.quality_score or 0))
    lines = ["# 投稿候補の一覧", "", "投稿向き度の高い順です。", "",
             "| 投稿向き度 | 元ファイル | 主役 | フォルダ | 状態 |", "|---|---|---|---|---|"]
    for r in ranked:
        score = f"{r.quality_score}/10" if r.quality_score is not None else "-"
        status = f"エラー: {r.error}" if r.error else "OK"
        lines.append(f"| {score} | {Path(r.source).name} | {r.subject or '-'} | {Path(r.folder).name} | {status} |")
    path = out_dir / "summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

