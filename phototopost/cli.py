"""コマンドの入口。

例:
    phototopost ~/Pictures/旅行 -o ~/Pictures/旅行_投稿用
    phototopost ./photos --platforms instagram,linkedin --strength 0.5
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .media import scan_folder
from .pipeline import Options, Pipeline, write_summary
from .platforms import PLATFORMS, parse_platforms
from .video import ffmpeg_available


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="phototopost",
        description="写真フォルダから SNS 投稿用の画像・動画と投稿文を作ります。",
    )
    ap.add_argument("folder", type=Path, help="写真・動画が入ったフォルダ")
    ap.add_argument("-o", "--output", type=Path, help="出力先（省略時は <フォルダ>_posts）")
    ap.add_argument(
        "-p", "--platforms",
        help=f"投稿先をカンマ区切りで（{', '.join(PLATFORMS)}, all）。省略時は "
        + ", ".join(k for k, p in PLATFORMS.items() if p.default),
    )
    ap.add_argument("--strength", type=float, default=0.7, help="補正の強さ 0〜1（0 で補正なし）")
    ap.add_argument("-r", "--recursive", action="store_true", help="サブフォルダも読み込む")
    ap.add_argument("--no-ai", action="store_true", help="AI を使わない（補正とトリミングだけ）")
    ap.add_argument("--style-file", type=Path, help="過去の投稿例を書いたテキストファイル（文体を似せる）")
    ap.add_argument("--use-location", action="store_true", help="撮影場所の位置情報を AI に渡す")
    ap.add_argument("--limit", type=int, help="処理する件数の上限（お試し用）")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.folder.is_dir():
        print(f"フォルダが見つかりません: {args.folder}", file=sys.stderr)
        return 2
    try:
        platforms = parse_platforms(args.platforms)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2

    use_ai = not args.no_ai
    if use_ai and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print(
            "ANTHROPIC_API_KEY が設定されていません。投稿文の作成には API キーが必要です。\n"
            "補正とトリミングだけ行う場合は --no-ai を付けてください。",
            file=sys.stderr,
        )
        return 2

    items = scan_folder(args.folder, args.recursive)
    if args.limit:
        items = items[: args.limit]
    if not items:
        print("写真・動画が見つかりませんでした。", file=sys.stderr)
        return 1
    if any(i.kind == "video" for i in items) and not ffmpeg_available():
        print("※ FFmpeg が見つからないため、動画はスキップされます。", file=sys.stderr)

    out_dir = args.output or args.folder.with_name(args.folder.name + "_posts")
    out_dir.mkdir(parents=True, exist_ok=True)
    style = args.style_file.read_text(encoding="utf-8") if args.style_file else None
    pipeline = Pipeline(
        Options(platforms, args.strength, use_ai, args.use_location, style), out_dir
    )

    print(f"{len(items)} 件を処理します → {out_dir}")
    results = []
    for n, item in enumerate(items, 1):
        print(f"[{n}/{len(items)}] {item.path.name} ...", end=" ", flush=True)
        r = pipeline.process(item)
        results.append(r)
        print(f"エラー: {r.error}" if r.error else "OK")

    summary = write_summary(out_dir, results)
    failed = sum(1 for r in results if r.error)
    print(f"\n完了: {len(results) - failed} 件成功 / {failed} 件エラー")
    print(f"一覧: {summary}")
    return 1 if failed == len(results) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
