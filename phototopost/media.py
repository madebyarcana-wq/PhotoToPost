"""フォルダの走査と、写真の読み込み・撮影情報の取得。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import ExifTags, Image, ImageOps

try:  # iPhone の HEIC を読めるようにする
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


@dataclass
class MediaItem:
    path: Path
    kind: str  # "photo" or "video"
    taken_at: datetime | None = None
    gps: tuple[float, float] | None = None
    camera: str | None = None


def scan_folder(folder: Path, recursive: bool = False) -> list[MediaItem]:
    pattern = "**/*" if recursive else "*"
    items = []
    for path in sorted(folder.glob(pattern)):
        if not path.is_file() or path.name.startswith("."):
            continue
        ext = path.suffix.lower()
        if ext in PHOTO_EXTS:
            items.append(MediaItem(path, "photo"))
        elif ext in VIDEO_EXTS:
            items.append(MediaItem(path, "video"))
    return items


def load_photo(item: MediaItem) -> Image.Image:
    """写真を開き、向きを直して RGB で返す。撮影情報も item に書き込む。"""
    with Image.open(item.path) as img:
        _read_exif(item, img)
        img = ImageOps.exif_transpose(img)
        return img.convert("RGB")


def _read_exif(item: MediaItem, img: Image.Image) -> None:
    exif = img.getexif()
    if not exif:
        return
    sub = exif.get_ifd(ExifTags.IFD.Exif)
    raw = sub.get(ExifTags.Base.DateTimeOriginal) or exif.get(ExifTags.Base.DateTime)
    if raw:
        try:
            item.taken_at = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            pass
    model = exif.get(ExifTags.Base.Model)
    if model:
        item.camera = str(model).strip("\x00 ").strip()
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    if gps:
        item.gps = _gps_to_degrees(gps)


def _gps_to_degrees(gps: dict) -> tuple[float, float] | None:
    try:
        lat = _dms(gps[2]) * (-1 if gps.get(1) == "S" else 1)
        lon = _dms(gps[4]) * (-1 if gps.get(3) == "W" else 1)
        return (round(lat, 5), round(lon, 5))
    except (KeyError, TypeError, ZeroDivisionError, IndexError):
        return None


def _dms(value) -> float:
    d, m, s = (float(v) for v in value)
    return d + m / 60 + s / 3600
