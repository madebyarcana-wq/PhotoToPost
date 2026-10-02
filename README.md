# PhotoToPost

写真フォルダを読み込んで、SNS 投稿用に **画像の補正・トリミング** と **投稿文の作成** をまとめて行うツールです。

- 対応する投稿先: **Instagram / X / Threads**（標準）、**LinkedIn**（試験的。指定したときだけ出力）
- 対応ファイル: 写真（JPG / HEIC / PNG / WebP / TIFF）、動画（MP4 / MOV など）
- 文章のトーン: 個人の日常投稿

## できること

| 処理 | 内容 |
|---|---|
| 補正 | 向きの修正、色かぶりの軽減、明るさ・コントラスト・彩度の調整、軽いシャープ |
| トリミング | AI が見つけた主役を中心に、投稿先に合う比率で切り出し（Instagram 4:5/1:1/3:4、X 16:9/1:1/4:5 など） |
| 動画 | 投稿先の比率（リールは 9:16）への切り出し、長さの上限内へのカット（見どころから開始）、カバー画像の作成 |
| 投稿文 | 投稿先ごとの文体・文字数でキャプションとハッシュタグを作成（X は全角を 2 文字として数えて調整） |
| 選定の手助け | 各写真に「投稿向き度（1〜10）」を付け、一覧を高い順に並べる |
| プライバシー | 出力画像から撮影場所などの情報（EXIF）を削除。位置情報は `--use-location` を付けたときだけ AI に渡す |

## 準備

1. **Python 3.10 以上** をインストール
2. **FFmpeg** をインストール（動画を扱う場合のみ）
   - Mac: `brew install ffmpeg`
   - Windows: `winget install ffmpeg`
3. このツールをインストール
   ```bash
   cd PhotoToPost
   python -m venv .venv
   source .venv/bin/activate        # Windows は .venv\Scripts\activate
   pip install -e .
   ```
4. **Claude Code を入れてログイン**（claude.ai の有料プラン Pro / Max の範囲で使えます）
   - Mac: `curl -fsSL https://claude.ai/install.sh | bash`
   - Windows（PowerShell）: `irm https://claude.ai/install.ps1 | iex`
   - インストール後、一度 `claude` と入力して起動し、表示に従って **claude.ai のアカウントでログイン** します。ログインできたら `/exit` で終了して構いません。

   このツールは裏で `claude` コマンドを呼び出して写真を見せ、投稿文を作ってもらいます。API キーや追加の料金は不要です。

## 使い方

```bash
# 基本（Instagram / X / Threads 向けに出力）
phototopost ~/Pictures/週末の散歩

# 出力先を指定し、まずは 3 件だけ試す
phototopost ~/Pictures/週末の散歩 -o ~/Desktop/投稿用 --limit 3

# LinkedIn も出力する / すべての投稿先
phototopost ~/Pictures/週末の散歩 -p instagram,x,threads,linkedin
phototopost ~/Pictures/週末の散歩 -p all

# 補正を弱めにする（0 で補正なし、1 で最大）
phototopost ~/Pictures/週末の散歩 --strength 0.4

# AI を使わず補正とトリミングだけ
phototopost ~/Pictures/週末の散歩 --no-ai
```

### 文章を自分らしくするコツ

- **過去の投稿を見本にする**: 自分の過去の投稿を 3〜5 件テキストファイルに貼り付けて `--style-file 過去の投稿.txt` を付けると、言葉づかいや絵文字の量を似せます。
- **写真ごとにメモを添える**: 写真と同じ名前の `.txt`（例: `IMG_0001.jpg` に対して `IMG_0001.txt`）に「母と散歩。久しぶりの晴れ」のように書いておくと、その内容を踏まえた文章になります。写真から分からない店名や人の名前は、こうして伝えてください。

## 出力

```
週末の散歩_posts/
├── summary.md              ← 全体の一覧（投稿向き度の高い順）
├── results.json            ← 同じ内容のデータ
├── photo_IMG_0001/
│   ├── instagram.jpg
│   ├── x.jpg
│   ├── threads.jpg
│   └── post.md             ← 投稿先ごとの投稿文（文字数つき）
└── video_IMG_0002/
    ├── instagram.mp4 / instagram_cover.jpg
    ├── x.mp4 / x_cover.jpg
    ├── threads.mp4 / threads_cover.jpg
    └── post.md
```

## 料金と利用上限

- 標準では claude.ai の有料プランの範囲で動くので、**追加の料金はかかりません**。
- ただしプランには一定時間あたりの利用上限があり、写真 1 枚（動画は 3 場面）ごとに 1 回 Claude を使います。
  大量の写真を一度に処理すると上限に達することがあるので、`--limit` で少しずつ処理するのがおすすめです。
  上限に達した写真はエラーとして一覧に残るので、時間をおいて再実行してください。
- 使うモデルはプランの標準です。変えたい場合は環境変数 `PHOTOTOPOST_MODEL`（例: `sonnet`、`opus`）で指定できます。
- API キー（従量課金）で動かしたい場合は `--ai api` を付け、環境変数 `ANTHROPIC_API_KEY` を設定してください。

## 投稿先を増やす・仕様を変える

投稿先の仕様（比率・サイズ・文字数・ハッシュタグ数・文体の指示）は `phototopost/platforms.py` にまとめてあります。
TikTok などを増やすときは、ここに 1 項目足すだけで動きます。各 SNS の仕様は変わることがあるので、ときどき公式ヘルプで確認してください。

## 今後の予定（案）

- 似た写真をまとめて、ベストショットだけを選ぶ
- 複数枚をまとめた投稿（カルーセル）の文章作成
- 画面で結果を見ながら選び直し・文章の修正ができる Web 画面
- 各 SNS への自動投稿（各社の API 申請が必要）

## 開発

```bash
pip install -e ".[dev]"
pytest
```
