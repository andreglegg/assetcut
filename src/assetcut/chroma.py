from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from assetcut.alpha import clear_rgb_where_alpha_zero
from assetcut.image_io import ensure_rgba

BoolMask = NDArray[np.bool_]

DEFAULT_TOLERANCE = 60
"""Euclidean RGB distance from the key color that still counts as background."""

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class ChromaKey:
    color: RGB
    background: BoolMask
    ratio: float


def parse_hex_color(value: str) -> RGB:
    text = value.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"Key color must be a 6-digit hex value like ff00ff: {value}")
    try:
        r = int(text[0:2], 16)
        g = int(text[2:4], 16)
        b = int(text[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"Key color is not valid hex: {value}") from exc
    return (r, g, b)


def _border_pixels(rgb: NDArray[np.uint8], thickness: int = 2) -> NDArray[np.uint8]:
    height, width = rgb.shape[:2]
    thickness = max(1, min(thickness, height, width))
    top = rgb[:thickness, :, :].reshape(-1, 3)
    bottom = rgb[-thickness:, :, :].reshape(-1, 3)
    left = rgb[:, :thickness, :].reshape(-1, 3)
    right = rgb[:, -thickness:, :].reshape(-1, 3)
    return np.concatenate([top, bottom, left, right], axis=0)


def detect_key_color(rgb: NDArray[np.uint8], border_thickness: int = 2) -> tuple[RGB, float]:
    """Return the dominant border color and the fraction of border it covers."""
    border = _border_pixels(rgb, border_thickness).astype(np.int16)
    quantized = (border // 16) * 16
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    mode = colors[int(counts.argmax())]
    near_mode = np.abs(border - mode).max(axis=1) <= 24
    center = border[near_mode].mean(axis=0).round().astype(int)
    # Dominance is how much of the border clusters near this color, robust to the
    # quantization splitting one key across adjacent buckets.
    near_center = np.abs(border - center).max(axis=1) <= 32
    fraction = float(near_center.mean())
    color = (int(center[0]), int(center[1]), int(center[2]))
    return color, fraction


def chroma_mask(rgb: NDArray[np.uint8], key_color: RGB, tolerance: float) -> BoolMask:
    diff = rgb.astype(np.float32) - np.array(key_color, dtype=np.float32)
    distance = np.sqrt(np.sum(diff * diff, axis=2))
    return np.asarray(distance <= tolerance, dtype=np.bool_)


def _is_saturated(color: RGB, min_spread: int = 60) -> bool:
    return (max(color) - min(color)) >= min_spread


def detect_chroma_key(
    image: Image.Image,
    tolerance: float = DEFAULT_TOLERANCE,
    min_background_ratio: float = 0.12,
    border_dominance: float = 0.80,
    require_saturated: bool = True,
) -> ChromaKey | None:
    """Detect a flat solid-color background suitable for chroma keying.

    When ``require_saturated`` is True (used by auto backend selection) only vivid
    keys such as magenta or green screens qualify, so neutral photo backgrounds are
    left to the model backends.
    """
    rgba = ensure_rgba(image)
    arr = np.array(rgba, dtype=np.uint8)
    if np.any(arr[:, :, 3] < 255):
        return None

    rgb = arr[:, :, :3]
    height, width = rgb.shape[:2]
    if width < 8 or height < 8:
        return None

    key_color, fraction = detect_key_color(rgb)
    if fraction < border_dominance:
        return None
    if require_saturated and not _is_saturated(key_color):
        return None

    mask = chroma_mask(rgb, key_color, tolerance)
    ratio = float(mask.mean())
    if ratio < min_background_ratio or ratio > 0.98:
        return None

    return ChromaKey(color=key_color, background=mask, ratio=ratio)


def _despill(arr: NDArray[np.uint8], background: BoolMask, key_color: RGB) -> None:
    """Reduce key-color spill on the 1px foreground ring touching the background."""
    foreground = ~background
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    grown = cv2.dilate(background.astype(np.uint8), kernel, iterations=1).astype(bool)
    fringe = foreground & grown
    if not np.any(fringe):
        return

    key = np.array(key_color, dtype=np.int16)
    high = key > int(key.mean())
    if not np.any(high) or np.all(high):
        return

    pixels = arr[fringe, :3].astype(np.int16)
    low_max = pixels[:, ~high].max(axis=1)
    for channel in np.where(high)[0]:
        pixels[:, channel] = np.minimum(pixels[:, channel], low_max)
    arr[fringe, :3] = pixels.astype(np.uint8)


def remove_chroma_key(
    image: Image.Image,
    key_color: RGB | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
    despill: bool = True,
    expand_pixels: int = 0,
) -> Image.Image:
    """Cut a solid-color background and return an RGBA image with binary alpha.

    ``key_color`` defaults to the dominant border color. Unlike the checkerboard
    backend this keys on color, so enclosed background regions (hollow tile centers)
    are removed too.
    """
    rgba = ensure_rgba(image)
    arr = np.array(rgba, dtype=np.uint8)
    rgb = arr[:, :, :3]

    if key_color is None:
        key_color, _ = detect_key_color(rgb)

    background = chroma_mask(rgb, key_color, tolerance)
    if not np.any(background):
        raise RuntimeError(
            "No background matching the key color "
            f"{key_color} was found. Try a higher --tolerance or set --key-color."
        )

    if expand_pixels > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        background = cv2.dilate(
            background.astype(np.uint8), kernel, iterations=expand_pixels
        ).astype(bool)

    if despill:
        _despill(arr, background, key_color)

    arr[background, 3] = 0
    arr[~background, 3] = 255
    return clear_rgb_where_alpha_zero(Image.fromarray(arr, mode="RGBA"))
