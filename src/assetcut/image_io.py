from __future__ import annotations

from pathlib import Path

from PIL import Image

SUPPORTED_INPUT_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def load_image(path: Path) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(f"Input image does not exist: {path}")
    image = Image.open(path)
    image.load()
    return image


def ensure_rgba(image: Image.Image) -> Image.Image:
    if image.mode == "RGBA":
        return image
    if image.mode == "LA":
        return image.convert("RGBA")
    if image.mode == "P" and "transparency" in image.info:
        return image.convert("RGBA")
    return image.convert("RGBA")


def save_png_rgba(image: Image.Image, path: Path) -> Path:
    if path.suffix.lower() != ".png":
        raise ValueError(f"Output path must end in .png: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    rgba = ensure_rgba(image)
    rgba.save(path, format="PNG")
    return path


def iter_image_files(folder: Path, recursive: bool) -> list[Path]:
    if not folder.exists():
        raise FileNotFoundError(f"Input folder does not exist: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Input path is not a folder: {folder}")

    pattern = "**/*" if recursive else "*"
    files = [
        path
        for path in folder.glob(pattern)
        if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES
    ]
    return sorted(files)
