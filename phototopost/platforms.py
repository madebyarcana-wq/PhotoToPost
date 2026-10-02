"""投稿先ごとの仕様。

新しい投稿先を増やすときは、このファイルの PLATFORMS に Platform を 1 つ足すだけでよい。
各 SNS の仕様は変わることがあるので、数値は公式ヘルプで定期的に確認すること。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Platform:
    key: str
    label: str
    # 写真のトリミング候補（幅:高さ）。元の写真に一番近い比率が選ばれる。
    photo_ratios: tuple[tuple[int, int], ...]
    # 出力する写真の長辺ピクセル数
    photo_long_edge: int
    # 動画の出力比率と長さの上限（秒）
    video_ratio: tuple[int, int]
    video_max_seconds: int
    # 投稿文の上限文字数。weighted_count=True なら X 方式（全角を 2 と数える）。
    caption_max: int
    weighted_count: bool = False
    hashtags_max: int = 5
    # AI に渡す書き方の指示
    style_hint: str = ""
    # 標準で出力するか（False なら --platforms で明示したときだけ出力）
    default: bool = True
    notes: tuple[str, ...] = field(default_factory=tuple)


PLATFORMS: dict[str, Platform] = {
    p.key: p
    for p in [
        Platform(
            key="instagram",
            label="Instagram",
            photo_ratios=((4, 5), (1, 1), (3, 4)),
            photo_long_edge=1440,
            video_ratio=(9, 16),
            video_max_seconds=90,
            caption_max=2200,
            hashtags_max=5,
            style_hint=(
                "写真が主役。1行目で情景が浮かぶ一言、そのあと2〜4行で気持ちや小さな発見。"
                "適度に改行し、絵文字は0〜2個。ハッシュタグは最後にまとめる。"
            ),
        ),
        Platform(
            key="x",
            label="X",
            photo_ratios=((16, 9), (1, 1), (4, 5)),
            photo_long_edge=1600,
            video_ratio=(16, 9),
            video_max_seconds=140,
            caption_max=280,
            weighted_count=True,
            hashtags_max=1,
            style_hint="短く一言でつぶやく。ハッシュタグは基本なし、付けても1個。",
        ),
        Platform(
            key="threads",
            label="Threads",
            photo_ratios=((4, 5), (1, 1)),
            photo_long_edge=1440,
            video_ratio=(9, 16),
            video_max_seconds=300,
            caption_max=500,
            hashtags_max=1,
            style_hint="友だちに話しかけるような会話調。問いかけで終えると反応が来やすい。トピックタグは1個まで。",
        ),
        # LinkedIn は枠だけ用意。--platforms linkedin を指定したときだけ出力する。
        Platform(
            key="linkedin",
            label="LinkedIn",
            photo_ratios=((1, 1), (4, 5), (191, 100)),
            photo_long_edge=1200,
            video_ratio=(1, 1),
            video_max_seconds=600,
            caption_max=3000,
            hashtags_max=3,
            style_hint=(
                "日常の出来事から学びや気づきを1つ添える。くだけすぎない丁寧な文体。"
                "冒頭2行で要点が伝わるように。"
            ),
            default=False,
            notes=("試験的な対応です。",),
        ),
    ]
}


def default_platforms() -> list[Platform]:
    return [p for p in PLATFORMS.values() if p.default]


def parse_platforms(spec: str | None) -> list[Platform]:
    """'instagram,x' のような指定を Platform のリストに変換する。"""
    if not spec:
        return default_platforms()
    result = []
    for key in (s.strip().lower() for s in spec.split(",")):
        if not key:
            continue
        if key == "all":
            return list(PLATFORMS.values())
        if key not in PLATFORMS:
            raise ValueError(f"未対応の投稿先です: {key}（対応: {', '.join(PLATFORMS)}）")
        if PLATFORMS[key] not in result:
            result.append(PLATFORMS[key])
    return result
