from __future__ import annotations

from pathlib import Path

from PIL import Image

from assetcut.image_io import ensure_rgba, iter_image_files, load_image, save_png_rgba

LIGHT = (246, 246, 246, 255)
DARK = (22, 24, 28, 255)
COLOR = (38, 72, 82, 255)
GAP = 16


def default_preview_path(path: Path, out: Path | None = None) -> Path:
    if out is not None:
        return out
    if path.is_dir():
        return path.with_name(f"{path.name}-preview.png")
    return path.with_name(f"{path.stem}-preview.png")


def discover_cutout_path(input_path: Path, cutout: Path | None = None) -> Path:
    if cutout is not None:
        return cutout
    candidate = input_path.with_name(f"{input_path.stem}-cutout.png")
    if candidate.exists():
        return candidate
    return input_path


def create_file_preview(
    input_path: Path,
    output_path: Path,
    cutout_path: Path | None = None,
    tile_size: int = 256,
) -> Path:
    source = ensure_rgba(load_image(input_path))
    cutout = ensure_rgba(load_image(discover_cutout_path(input_path, cutout_path)))

    tiles = [
        _fit_on_background(source, tile_size, LIGHT),
        _fit_on_background(cutout, tile_size, LIGHT),
        _fit_on_background(cutout, tile_size, DARK),
        _fit_on_background(cutout, tile_size, COLOR),
    ]
    preview = _join_tiles(tiles, columns=4, tile_size=tile_size)
    return save_png_rgba(preview, output_path)


def create_folder_preview(
    folder: Path,
    output_path: Path,
    recursive: bool,
    tile_size: int = 180,
    max_items: int = 40,
) -> Path:
    files = iter_image_files(folder, recursive=recursive)[:max_items]
    if not files:
        raise FileNotFoundError(f"No images found in folder: {folder}")

    tiles: list[Image.Image] = []
    for path in files:
        cutout = ensure_rgba(load_image(path))
        tiles.append(_fit_on_background(cutout, tile_size, LIGHT))
        tiles.append(_fit_on_background(cutout, tile_size, DARK))

    preview = _join_tiles(tiles, columns=4, tile_size=tile_size)
    return save_png_rgba(preview, output_path)


def _fit_on_background(
    image: Image.Image,
    tile_size: int,
    background: tuple[int, int, int, int],
) -> Image.Image:
    tile = Image.new("RGBA", (tile_size, tile_size), background)
    content = ensure_rgba(image).copy()
    content.thumbnail((tile_size - GAP * 2, tile_size - GAP * 2), Image.Resampling.LANCZOS)
    x = (tile_size - content.size[0]) // 2
    y = (tile_size - content.size[1]) // 2
    tile.alpha_composite(content, (x, y))
    return tile


def _join_tiles(
    tiles: list[Image.Image],
    columns: int,
    tile_size: int,
) -> Image.Image:
    rows = (len(tiles) + columns - 1) // columns
    width = columns * tile_size + (columns + 1) * GAP
    height = rows * tile_size + (rows + 1) * GAP
    canvas = Image.new("RGBA", (width, height), (236, 236, 236, 255))

    for index, tile in enumerate(tiles):
        row = index // columns
        column = index % columns
        x = GAP + column * (tile_size + GAP)
        y = GAP + row * (tile_size + GAP)
        canvas.alpha_composite(tile, (x, y))

    return canvas
