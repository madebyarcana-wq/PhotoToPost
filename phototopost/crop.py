"""主役の位置を中心にしたトリミング。"""

from __future__ import annotations

import numpy as np
from PIL import Image

Ratio = tuple[int, int]


def choose_ratio(width: int, height: int, ratios: tuple[Ratio, ...]) -> Ratio:
    """元の写真の比率に一番近い候補を選ぶ（切り取られる部分が最も少なくなる）。"""
    src = width / height
    return min(ratios, key=lambda r: abs(np.log(src / (r[0] / r[1]))))


def crop_box(
    width: int, height: int, ratio: Ratio, focus: tuple[float, float] = (0.5, 0.5)
) -> tuple[int, int, int, int]:
    """比率 ratio で切り出せる最大の範囲を、focus（0〜1 の相対座標）が中心に来るように返す。"""
    target = ratio[0] / ratio[1]
    if width / height > target:
        ch, cw = height, round(height * target)
    else:
        cw, ch = width, round(width / target)
    fx, fy = focus
    left = int(round(np.clip(fx * width - cw / 2, 0, width - cw)))
    top = int(round(np.clip(fy * height - ch / 2, 0, height - ch)))
    return left, top, left + cw, top + ch


def crop_and_resize(
    img: Image.Image, ratio: Ratio, long_edge: int, focus: tuple[float, float]
) -> Image.Image:
    out = img.crop(crop_box(img.width, img.height, ratio, focus))
    scale = long_edge / max(out.size)
    if scale < 1:  # 拡大はしない
        out = out.resize(
            (round(out.width * scale), round(out.height * scale)), Image.Resampling.LANCZOS
        )
    return out


def estimate_focus(img: Image.Image) -> tuple[float, float]:
    """AI が使えないときの主役位置の推定。輪郭が集まっている場所の重心を使う。"""
    small = img.convert("L").resize((128, max(1, round(128 * img.height / img.width))))
    a = np.asarray(small, dtype=np.float32)
    gx = np.abs(np.diff(a, axis=1))[:-1, :]
    gy = np.abs(np.diff(a, axis=0))[:, :-1]
    energy = gx + gy
    total = energy.sum()
    if total <= 0:
        return (0.5, 0.5)
    ys, xs = np.mgrid[0 : energy.shape[0], 0 : energy.shape[1]]
    cx = float((energy * xs).sum() / total) / energy.shape[1]
    cy = float((energy * ys).sum() / total) / energy.shape[0]
    # 端に寄りすぎないよう中央と半々にする
    return (0.5 + (cx - 0.5) * 0.5, 0.5 + (cy - 0.5) * 0.5)
