from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from assetcut.image_io import ensure_rgba


@dataclass(frozen=True)
class AlphaStats:
    has_alpha: bool
    min_alpha: int
    max_alpha: int
    transparent_pixels: int
    semi_transparent_pixels: int
    opaque_pixels: int
    total_pixels: int

    @property
    def has_real_transparency(self) -> bool:
        return self.has_alpha and self.min_alpha < 255 and self.transparent_pixels > 0


def alpha_stats(image: Image.Image) -> AlphaStats:
    has_alpha = image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    rgba = ensure_rgba(image)
    alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    total = int(alpha.size)
    transparent = int(np.count_nonzero(alpha == 0))
    opaque = int(np.count_nonzero(alpha == 255))
    semi = int(np.count_nonzero((alpha > 0) & (alpha < 255)))
    return AlphaStats(
        has_alpha=has_alpha,
        min_alpha=int(alpha.min()) if total else 255,
        max_alpha=int(alpha.max()) if total else 255,
        transparent_pixels=transparent,
        semi_transparent_pixels=semi,
        opaque_pixels=opaque,
        total_pixels=total,
    )


def clear_rgb_where_alpha_zero(image: Image.Image) -> Image.Image:
    rgba = ensure_rgba(image)
    arr = np.array(rgba, dtype=np.uint8)
    alpha = arr[:, :, 3]
    arr[alpha == 0, :3] = 0
    return Image.fromarray(arr, mode="RGBA")


def transparent_rgb_is_clean(image: Image.Image) -> bool:
    rgba = ensure_rgba(image)
    arr = np.array(rgba, dtype=np.uint8)
    transparent = arr[:, :, 3] == 0
    if not np.any(transparent):
        return True
    return bool(np.all(arr[transparent, :3] == 0))


def edge_matte_warning(image: Image.Image) -> str | None:
    rgba = ensure_rgba(image)
    arr = np.array(rgba, dtype=np.uint8)
    alpha = arr[:, :, 3]
    edge = (alpha > 0) & (alpha < 255)
    if not np.any(edge):
        return None

    edge_rgb = arr[edge, :3]
    channel_spread = edge_rgb.max(axis=1) - edge_rgb.min(axis=1)
    brightness = edge_rgb.mean(axis=1)
    pale_neutral = (channel_spread <= 12) & (brightness >= 210)
    ratio = float(np.count_nonzero(pale_neutral)) / float(edge_rgb.shape[0])
    if ratio >= 0.35:
        return "Semi-transparent edge pixels look like white or gray matte contamination."
    return None


def trim_to_alpha(image: Image.Image, threshold: int = 1) -> Image.Image:
    rgba = ensure_rgba(image)
    arr = np.array(rgba, dtype=np.uint8)
    alpha = arr[:, :, 3]
    ys, xs = np.where(alpha >= threshold)
    if len(xs) == 0 or len(ys) == 0:
        return rgba
    left = int(xs.min())
    right = int(xs.max()) + 1
    top = int(ys.min())
    bottom = int(ys.max()) + 1
    return rgba.crop((left, top, right, bottom))


def add_transparent_padding(image: Image.Image, padding: int) -> Image.Image:
    rgba = ensure_rgba(image)
    if padding < 0:
        raise ValueError(f"Padding must be greater than or equal to 0: {padding}")
    if padding == 0:
        return rgba
    width, height = rgba.size
    out = Image.new("RGBA", (width + padding * 2, height + padding * 2), (0, 0, 0, 0))
    out.paste(rgba, (padding, padding))
    return out


def hard_alpha(image: Image.Image, threshold: int) -> Image.Image:
    rgba = ensure_rgba(image)
    arr = np.array(rgba, dtype=np.uint8)
    alpha = arr[:, :, 3]
    arr[:, :, 3] = np.where(alpha >= threshold, 255, 0).astype(np.uint8)
    arr[arr[:, :, 3] == 0, :3] = 0
    return Image.fromarray(arr, mode="RGBA")


def looks_like_baked_checkerboard(image: Image.Image) -> bool:
    rgba = ensure_rgba(image)
    arr = np.array(rgba, dtype=np.uint8)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]

    if np.any(alpha < 255):
        return False

    height, width = alpha.shape
    if width < 32 or height < 32:
        return False

    grayish = (
        (np.abs(rgb[:, :, 0].astype(np.int16) - rgb[:, :, 1].astype(np.int16)) < 8)
        & (np.abs(rgb[:, :, 1].astype(np.int16) - rgb[:, :, 2].astype(np.int16)) < 8)
        & (rgb[:, :, 0] >= 180)
        & (rgb[:, :, 0] <= 255)
    )
    gray_ratio = float(np.count_nonzero(grayish)) / float(grayish.size)
    if gray_ratio < 0.25:
        return False

    cell = max(4, min(width, height) // 32)
    sampled: list[int] = []
    for y in range(0, height - cell + 1, cell):
        for x in range(0, width - cell + 1, cell):
            patch = rgb[y : y + cell, x : x + cell, :]
            if patch.size == 0:
                continue
            sampled.append(int(np.mean(patch[:, :, 0])))

    if len(sampled) < 16:
        return False

    values = np.array(sampled, dtype=np.int16)
    spread = int(values.max() - values.min())
    return spread >= 20 and gray_ratio >= 0.35


def alpha_bbox(image: Image.Image, threshold: int = 1) -> tuple[int, int, int, int] | None:
    rgba = ensure_rgba(image)
    alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    ys, xs = np.where(alpha >= threshold)
    if len(xs) == 0 or len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def save_alpha_mask(image: Image.Image, path: Path) -> None:
    rgba = ensure_rgba(image)
    path.parent.mkdir(parents=True, exist_ok=True)
    rgba.getchannel("A").save(path)
