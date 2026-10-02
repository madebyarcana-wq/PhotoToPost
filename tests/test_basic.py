from pathlib import Path
import subprocess

import numpy as np
import pytest
from PIL import Image

from phototopost import ai
from phototopost.cli import main
from phototopost.crop import choose_ratio, crop_box
from phototopost.enhance import auto_enhance
from phototopost.platforms import PLATFORMS, parse_platforms
from phototopost.textutil import compose, count_chars, normalize_hashtags
from phototopost.video import ffmpeg_available


def make_photo(path: Path, size=(1200, 800), color=(90, 110, 160)):
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[:] = color
    arr[size[1] // 3 : size[1] // 2, size[0] // 2 : size[0] * 3 // 4] = (240, 200, 60)
    Image.fromarray(arr).save(path, "JPEG")


def test_default_platforms_exclude_linkedin():
    keys = [p.key for p in parse_platforms(None)]
    assert keys == ["instagram", "x", "threads"]
    assert [p.key for p in parse_platforms("linkedin, x")] == ["linkedin", "x"]
    with pytest.raises(ValueError):
        parse_platforms("tiktok")


def test_choose_ratio_and_crop_box():
    assert choose_ratio(3000, 4000, PLATFORMS["instagram"].photo_ratios) == (3, 4)
    assert choose_ratio(6000, 4000, PLATFORMS["x"].photo_ratios) == (16, 9)
    left, top, right, bottom = crop_box(4000, 3000, (1, 1), focus=(1.0, 0.5))
    assert (right - left, bottom - top) == (3000, 3000)
    assert right == 4000  # 右端に寄せても画像からはみ出さない


def test_auto_enhance_brightens_dark_photo():
    # 暗めのグラデーション（露出不足の写真の代わり）
    ramp = np.tile(np.linspace(10, 90, 100, dtype=np.uint8), (100, 1))
    dark = Image.fromarray(np.stack([ramp] * 3, axis=-1))
    out = auto_enhance(dark, 1.0)
    assert np.asarray(out).mean() > np.asarray(dark).mean()
    assert auto_enhance(dark, 0) is dark


def test_x_weighted_count_and_compose():
    assert count_chars("abc", weighted=True) == 3
    assert count_chars("あいう", weighted=True) == 6
    text = compose("あ" * 139, ["旅行"], 280, weighted=True)
    assert text == "あ" * 139  # タグを入れると超えるのでタグを外す
    long = compose("今日はいい天気。" * 40, [], 280, weighted=True)
    assert count_chars(long, True) <= 280
    assert normalize_hashtags(["#旅行", "旅行", " 海 辺 "], 5) == ["#旅行", "#海辺"]


def test_cli_no_ai(tmp_path):
    src = tmp_path / "photos"
    src.mkdir()
    make_photo(src / "a.jpg")
    make_photo(src / "b.jpg", size=(800, 1200))
    out = tmp_path / "out"
    assert main([str(src), "-o", str(out), "--no-ai"]) == 0
    folder = out / "photo_b"
    with Image.open(folder / "instagram.jpg") as im:
        assert abs(im.width / im.height - 3 / 4) < 0.01
        assert not im.getexif()
    assert (folder / "post.md").exists()
    assert (out / "summary.md").exists()


class FakeWriter:
    def __init__(self, platforms, style_examples=None):
        self.platforms = platforms

    def analyze(self, item, frames, duration=None, use_location=False, note=None):
        return ai.Analysis(
            description="青い空と黄色い看板", subject="看板", focus_x=0.6, focus_y=0.4,
            quality_score=8, quality_notes="明るく構図がよい", highlight_start_seconds=0.5,
            captions=[
                ai.PlatformCaption(platform=p.key, text=f"{p.label}向けの文章", hashtags=["散歩", "空"])
                for p in self.platforms
            ],
        )


def test_cli_with_mocked_ai(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr("phototopost.pipeline.CaptionWriter", FakeWriter)
    src = tmp_path / "photos"
    src.mkdir()
    make_photo(src / "a.jpg")
    out = tmp_path / "out"
    assert main([str(src), "-o", str(out), "-p", "all"]) == 0
    post = (out / "photo_a" / "post.md").read_text(encoding="utf-8")
    assert "LinkedIn向けの文章" in post
    assert "Threads向けの文章\n\n#散歩" in post  # Threads はタグ 1 個まで
    assert "#空" not in post.split("## Threads")[1].split("##")[0]
    assert "8/10" in (out / "summary.md").read_text(encoding="utf-8")


@pytest.mark.skipif(not ffmpeg_available(), reason="FFmpeg がない")
def test_video(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr("phototopost.pipeline.CaptionWriter", FakeWriter)
    src = tmp_path / "videos"
    src.mkdir()
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=640x360:rate=24",
         str(src / "clip.mp4")], check=True,
    )
    out = tmp_path / "out"
    assert main([str(src), "-o", str(out), "-p", "instagram,x"]) == 0
    from phototopost.video import probe

    ig = probe(out / "video_clip" / "instagram.mp4")
    assert abs(ig.width / ig.height - 9 / 16) < 0.02
    assert (out / "video_clip" / "x_cover.jpg").exists()
