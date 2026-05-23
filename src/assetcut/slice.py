from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from assetcut.alpha import add_transparent_padding, trim_to_alpha
from assetcut.chroma import RGB, detect_chroma_key, remove_chroma_key
from assetcut.image_io import ensure_rgba, load_image, save_png_rgba
from assetcut.models import get_backend


@dataclass(frozen=True)
class Tile:
    index: int
    image: Image.Image
    x: int
    y: int
    width: int
    height: int
    row: int | None = None
    col: int | None = None

    def to_dict(self, filename: str | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {
            "index": self.index,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "row": self.row,
            "col": self.col,
        }
        if filename is not None:
            data["file"] = filename
        return data


@dataclass(frozen=True)
class SliceResult:
    tiles: list[Tile]
    mode: str
    columns: int | None = None
    rows: int | None = None
    tile_width: int | None = None
    tile_height: int | None = None


def _has_content(image: Image.Image, alpha_threshold: int) -> bool:
    alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)
    return bool(alpha.size and int(alpha.max()) >= alpha_threshold)


def _finish(image: Image.Image, trim_tiles: bool, pad: int, alpha_threshold: int) -> Image.Image:
    out = image
    if trim_tiles:
        out = trim_to_alpha(out, threshold=max(1, alpha_threshold))
    if pad > 0:
        out = add_transparent_padding(out, pad)
    return out


def slice_grid(
    image: Image.Image,
    tile_width: int,
    tile_height: int,
    margin: int = 0,
    spacing: int = 0,
    drop_empty: bool = True,
    trim_tiles: bool = False,
    pad: int = 0,
    alpha_threshold: int = 1,
) -> SliceResult:
    """Cut a fixed grid of cells, optionally dropping empty ones."""
    if tile_width <= 0 or tile_height <= 0:
        raise ValueError("Tile width and height must be positive.")
    if margin < 0 or spacing < 0:
        raise ValueError("Margin and spacing must be zero or positive.")

    rgba = ensure_rgba(image)
    width, height = rgba.size
    columns = (width - 2 * margin + spacing) // (tile_width + spacing)
    rows = (height - 2 * margin + spacing) // (tile_height + spacing)
    if columns <= 0 or rows <= 0:
        raise ValueError(
            f"Tile size {tile_width}x{tile_height} does not fit image {width}x{height}."
        )

    tiles: list[Tile] = []
    index = 0
    for row in range(rows):
        for col in range(columns):
            x = margin + col * (tile_width + spacing)
            y = margin + row * (tile_height + spacing)
            cell = rgba.crop((x, y, x + tile_width, y + tile_height))
            if drop_empty and not _has_content(cell, alpha_threshold):
                continue
            finished = _finish(cell, trim_tiles, pad, alpha_threshold)
            # x/y/width/height describe the source cell in the sheet; the saved image
            # may be smaller/larger when trim or pad is applied.
            tiles.append(
                Tile(index, finished, x, y, tile_width, tile_height, row=row, col=col)
            )
            index += 1

    return SliceResult(
        tiles=tiles,
        mode="grid",
        columns=columns,
        rows=rows,
        tile_width=tile_width,
        tile_height=tile_height,
    )


def _reading_order(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Sort (x, y, w, h) boxes top-to-bottom then left-to-right, clustering rows."""
    if not boxes:
        return []
    by_top = sorted(boxes, key=lambda b: (b[1], b[0]))
    median_height = float(np.median([b[3] for b in by_top]))
    tolerance = max(4.0, median_height * 0.5)

    ordered: list[tuple[int, int, int, int]] = []
    current: list[tuple[int, int, int, int]] = []
    baseline = by_top[0][1]
    for box in by_top:
        if box[1] - baseline > tolerance:
            ordered.extend(sorted(current, key=lambda b: b[0]))
            current = []
            baseline = box[1]
        current.append(box)
    ordered.extend(sorted(current, key=lambda b: b[0]))
    return ordered


def slice_auto(
    image: Image.Image,
    alpha_threshold: int = 1,
    min_area: int = 64,
    pad: int = 0,
    trim_tiles: bool = True,
) -> SliceResult:
    """Extract each connected opaque region as its own tile (gaps split tiles)."""
    rgba = ensure_rgba(image)
    alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    mask = (alpha >= alpha_threshold).astype(np.uint8)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

    boxes: list[tuple[int, int, int, int]] = []
    for label in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[label])
        if area < min_area:
            continue
        boxes.append((x, y, w, h))

    tiles: list[Tile] = []
    for index, (x, y, w, h) in enumerate(_reading_order(boxes)):
        cell = rgba.crop((x, y, x + w, y + h))
        finished = _finish(cell, trim_tiles, pad, alpha_threshold)
        # x/y/width/height describe the detected region in the source sheet; pad
        # only changes the saved image, not the recorded source rectangle.
        tiles.append(Tile(index, finished, x, y, w, h))

    return SliceResult(tiles=tiles, mode="auto")


@dataclass(frozen=True)
class SliceRunResult:
    input_path: Path
    output_folder: Path
    manifest_path: Path
    tile_count: int
    mode: str
    backend: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "input": str(self.input_path),
            "output_folder": str(self.output_folder),
            "manifest": str(self.manifest_path),
            "tiles": self.tile_count,
            "mode": self.mode,
            "backend": self.backend,
        }


def _prepare_transparency(
    image: Image.Image,
    backend: str,
    key_color: RGB | None,
    tolerance: float,
) -> tuple[Image.Image, str]:
    rgba = ensure_rgba(image)
    arr = np.asarray(rgba)
    has_alpha = bool(np.any(arr[:, :, 3] == 0)) and bool(np.any(arr[:, :, 3] > 0))
    normalized = backend.strip().lower()

    if normalized == "none":
        return rgba, "none"

    if normalized == "alpha":
        if not has_alpha:
            raise RuntimeError(
                "Image has no transparency to slice on. Use --backend chroma or --key-color."
            )
        return rgba, "alpha"

    if normalized == "chroma":
        return remove_chroma_key(rgba, key_color=key_color, tolerance=tolerance), "chroma"

    if normalized == "auto":
        if key_color is not None:
            return remove_chroma_key(rgba, key_color=key_color, tolerance=tolerance), "chroma"
        if has_alpha:
            return rgba, "alpha"
        if detect_chroma_key(rgba, tolerance=tolerance) is not None:
            return remove_chroma_key(rgba, key_color=None, tolerance=tolerance), "chroma"
        raise RuntimeError(
            "Could not find a background to slice on. The image has no transparency and "
            "no solid chroma-key background was detected. Pass --key-color, or "
            "--backend rembg, or --backend none for a grid with no background removal."
        )

    return get_backend(normalized).remove(rgba), normalized


def write_tiles(
    result: SliceResult,
    output_folder: Path,
    stem: str,
    overwrite: bool = False,
) -> Path:
    """Write each tile PNG plus a manifest.json; return the manifest path."""
    output_folder.mkdir(parents=True, exist_ok=True)
    manifest_path = output_folder / "manifest.json"
    if manifest_path.exists() and not overwrite:
        raise FileExistsError(
            f"Slice output already exists: {manifest_path}. Use --overwrite to replace it."
        )
    if overwrite:
        # Drop tiles from a previous run so a smaller result does not leave stragglers.
        # Match by literal prefix rather than glob so metacharacters in the stem
        # (e.g. "sheet[1]") do not silently skip the cleanup.
        prefix = f"{stem}_"
        for stale in output_folder.iterdir():
            if stale.name.startswith(prefix) and stale.suffix == ".png":
                stale.unlink()

    frames: list[dict[str, Any]] = []
    for tile in result.tiles:
        filename = f"{stem}_{tile.index:03d}.png"
        save_png_rgba(tile.image, output_folder / filename)
        frames.append(tile.to_dict(filename))

    manifest = {
        "source": stem,
        "mode": result.mode,
        "columns": result.columns,
        "rows": result.rows,
        "tile_width": result.tile_width,
        "tile_height": result.tile_height,
        "count": len(frames),
        "frames": frames,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def default_slice_folder(input_path: Path, out: Path | None = None) -> Path:
    if out is not None:
        return out
    return input_path.with_name(f"{input_path.stem}-tiles")


def run_slice(
    input_path: Path,
    out: Path | None = None,
    mode: str = "auto",
    tile_width: int | None = None,
    tile_height: int | None = None,
    margin: int = 0,
    spacing: int = 0,
    backend: str = "auto",
    key_color: RGB | None = None,
    tolerance: float = 60,
    drop_empty: bool = True,
    trim_tiles: bool | None = None,
    pad: int = 0,
    min_area: int = 64,
    alpha_threshold: int = 1,
    overwrite: bool = False,
) -> SliceRunResult:
    image = load_image(input_path)
    prepared, used_backend = _prepare_transparency(image, backend, key_color, tolerance)

    # Auto mode trims each tile tight to its content; grid mode keeps uniform cells
    # unless the caller asks otherwise.
    effective_trim = (mode == "auto") if trim_tiles is None else trim_tiles

    if mode == "grid":
        if not tile_width or not tile_height:
            raise ValueError("Grid mode needs a tile size, e.g. --tile 96x96.")
        result = slice_grid(
            prepared,
            tile_width=tile_width,
            tile_height=tile_height,
            margin=margin,
            spacing=spacing,
            drop_empty=drop_empty,
            trim_tiles=effective_trim,
            pad=pad,
            alpha_threshold=alpha_threshold,
        )
    elif mode == "auto":
        result = slice_auto(
            prepared,
            alpha_threshold=alpha_threshold,
            min_area=min_area,
            pad=pad,
            trim_tiles=effective_trim,
        )
    else:
        raise ValueError(f"Unknown slice mode: {mode}. Use 'auto' or 'grid'.")

    output_folder = default_slice_folder(input_path, out)
    manifest_path = write_tiles(result, output_folder, input_path.stem, overwrite=overwrite)

    return SliceRunResult(
        input_path=input_path,
        output_folder=output_folder,
        manifest_path=manifest_path,
        tile_count=len(result.tiles),
        mode=mode,
        backend=used_backend,
    )
