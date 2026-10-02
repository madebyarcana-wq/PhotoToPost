"""投稿文の文字数チェックと整形。"""

from __future__ import annotations

import re

# X の文字数の数え方（twitter-text v3）。この範囲の文字は 1、それ以外（日本語や絵文字）は 2。
_X_LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))
_URL_RE = re.compile(r"https?://\S+")


def _x_weight(ch: str) -> int:
    cp = ord(ch)
    return 1 if any(lo <= cp <= hi for lo, hi in _X_LIGHT_RANGES) else 2


def count_chars(text: str, weighted: bool) -> int:
    if not weighted:
        return len(text)
    total = 0
    for part in _URL_RE.split(text):
        total += sum(_x_weight(c) for c in part)
    return total + 23 * len(_URL_RE.findall(text))


def normalize_hashtags(tags: list[str], limit: int) -> list[str]:
    result = []
    for tag in tags:
        tag = re.sub(r"\s+", "", tag.strip()).lstrip("#＃")
        if tag and f"#{tag}" not in result:
            result.append(f"#{tag}")
    return result[:limit]


def compose(body: str, hashtags: list[str], limit: int, weighted: bool) -> str:
    """本文とハッシュタグをつなぎ、上限を超えたら タグ → 本文の末尾 の順に削る。"""
    body = body.strip()
    tags = list(hashtags)
    while True:
        text = body + ("\n\n" + " ".join(tags) if tags else "")
        if count_chars(text, weighted) <= limit:
            return text
        if tags:
            tags.pop()
            continue
        return truncate(body, limit, weighted)


def truncate(text: str, limit: int, weighted: bool) -> str:
    if count_chars(text, weighted) <= limit:
        return text
    ellipsis = "…"
    budget = limit - count_chars(ellipsis, weighted)
    out = ""
    for ch in text:
        if count_chars(out + ch, weighted) > budget:
            break
        out += ch
    # 文の切れ目があればそこで切る
    cut = max(out.rfind(p) for p in "。！？!?\n")
    if cut >= len(out) * 0.5:
        return out[: cut + 1].rstrip()
    return out.rstrip() + ellipsis
