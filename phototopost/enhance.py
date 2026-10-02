"""写真の自動補正（ホワイトバランス・明るさ・コントラスト・彩度・シャープ）。

やりすぎない補正を目指し、強さは strength（0〜1）でまとめて調整できる。
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


def auto_enhance(img: Image.Image, strength: float = 0.7) -> Image.Image:
    if strength <= 0:
        return img
    strength = min(strength, 1.0)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = _white_balance(arr, strength)
    arr = _levels(arr, strength)
    arr = _midtones(arr, strength)
    out = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8))
    return ImageEnhance.Color(out).enhance(1 + 0.12 * strength)


def sharpen_for_web(img: Image.Image, strength: float = 0.7) -> Image.Image:
    """縮小後にかける軽いシャープ。"""
    if strength <= 0:
        return img
    return img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=int(60 * strength), threshold=2))


def _luminance(arr: np.ndarray) -> np.ndarray:
    return arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722


def _white_balance(arr: np.ndarray, strength: float) -> np.ndarray:
    """グレーワールド法で色かぶりを弱める。夕焼けなどの雰囲気を消さないよう控えめに。"""
    lum = _luminance(arr)
    # 白飛び・黒つぶれは色の推定に使わない
    mask = (lum > 0.05) & (lum < 0.95)
    if mask.sum() < 100:
        return arr
    means = arr[mask].mean(axis=0)
    gray = means.mean()
    gains = np.clip(gray / np.maximum(means, 1e-4), 0.85, 1.18)
    gains = 1 + (gains - 1) * 0.6 * strength
    return arr * gains


def _levels(arr: np.ndarray, strength: float) -> np.ndarray:
    """暗部と明部の端を広げてコントラストを整える。"""
    lum = _luminance(arr)
    lo, hi = np.percentile(lum, [0.5, 99.5])
    if hi - lo < 0.05:  # ほぼ単色の画像は触らない
        return arr
    lo = min(lo, 0.12)  # 元から暗い・明るい写真を無理に伸ばさない
    hi = max(hi, 0.85)
    stretched = (arr - lo) / (hi - lo)
    return arr + (stretched - arr) * strength


def _midtones(arr: np.ndarray, strength: float) -> np.ndarray:
    """全体の明るさ（中間の明るさ）を自然な範囲に寄せる。"""
    median = float(np.median(_luminance(np.clip(arr, 0, 1))))
    if median <= 0.01:
        return arr
    target = 0.46
    # ガンマで中間の明るさを target に寄せる（変化量は制限する）
    gamma = np.log(target) / np.log(median)
    gamma = float(np.clip(gamma, 0.75, 1.3))
    gamma = 1 + (gamma - 1) * strength
    return np.power(np.clip(arr, 0, 1), gamma)
